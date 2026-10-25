"""Bounded LLM explanations.

The language model explains results; it never produces them. It can only see numbers by calling tools that run the
deterministic functions in risk.py, and every number in its answer is checked against those tool outputs. An answer
with an unsupported number is replaced by a deterministic template explanation. Without an API key, the template
is used directly.
"""

import json
import re
from collections.abc import Callable

from sqlalchemy import Connection

from app import repository, risk
from app.config import get_settings

MAX_TOOL_ROUNDS = 6

SYSTEM = """You explain flood-exposure results from the Risk Scenario Explorer to non-technical users.

Rules:
- Get every number from the tools. Never calculate, estimate, round, convert or invent numbers yourself.
- Quote numbers exactly as the tools return them (thousand separators are fine, e.g. 1,234,567 or 12.3%).
  Do not write "about", "roughly" or "million"-style approximations.
- If the tools cannot answer the question, say so plainly.
- The hazard data is illustrative, for demonstration only; mention this if the user asks about real-world risk.
- Answer in 2-5 short sentences of plain English."""

TOOLS = [
    {
        "name": "get_scenario_summary",
        "description": "Totals for one scenario: total and exposed population, exposed share, provinces per risk class, "
                       "and the most exposed provinces.",
        "input_schema": {
            "type": "object",
            "properties": {"scenario_id": {"type": "string", "description": "e.g. rp10, rp50, rp100, rp100_2050"}},
            "required": ["scenario_id"],
        },
    },
    {
        "name": "get_province_result",
        "description": "Exposed population, exposed share and risk class for one province under one scenario.",
        "input_schema": {
            "type": "object",
            "properties": {"scenario_id": {"type": "string"}, "province": {"type": "string"}},
            "required": ["scenario_id", "province"],
        },
    },
    {
        "name": "compare_scenarios",
        "description": "Change in exposed population from a base scenario to a target scenario, with the provinces "
                       "whose exposure grows most.",
        "input_schema": {
            "type": "object",
            "properties": {"base_scenario_id": {"type": "string"}, "target_scenario_id": {"type": "string"}},
            "required": ["base_scenario_id", "target_scenario_id"],
        },
    },
]


# ---------- tools: thin wrappers over the deterministic functions ----------

def run_tool(conn: Connection, name: str, args: dict) -> dict:
    if name == "get_scenario_summary":
        scenario = repository.get_scenario(conn, args["scenario_id"])
        return {"scenario": scenario, **risk.summarize(risk.province_results(repository.hazard_rows(conn, args["scenario_id"])))}
    if name == "get_province_result":
        results = risk.province_results(repository.hazard_rows(conn, args["scenario_id"]))
        match = next((r for r in results if r.province.lower() == args["province"].strip().lower()), None)
        if match is None:
            return {"error": f"No province named {args['province']!r}", "provinces": [r.province for r in results]}
        return {"scenario_id": args["scenario_id"], **match.__dict__}
    if name == "compare_scenarios":
        base = risk.province_results(repository.hazard_rows(conn, args["base_scenario_id"]))
        target = risk.province_results(repository.hazard_rows(conn, args["target_scenario_id"]))
        result = risk.compare(base, target)
        result.pop("all")  # keep the model's context small; the top changes are enough to explain
        return {"base_scenario_id": args["base_scenario_id"], "target_scenario_id": args["target_scenario_id"], **result}
    return {"error": f"Unknown tool {name}"}


# ---------- the number guard ----------

NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])\d+(?:\.\d+)?")


def numbers_in(text: str) -> set[float]:
    return {round(float(m.replace(",", "")), 1) for m in NUMBER.findall(text)}


def unsupported_numbers(answer: str, evidence: list[str]) -> list[str]:
    """Numbers in the answer that appear in none of the tool outputs or the question."""
    allowed = set().union(*(numbers_in(e) for e in evidence)) | {float(n) for n in range(0, 11)}
    return [m for m in NUMBER.findall(answer) if round(float(m.replace(",", "")), 1) not in allowed]


# ---------- template explanation (deterministic) ----------

def template_explanation(conn: Connection, scenario_id: str, compare_to: str | None) -> str:
    summary = run_tool(conn, "get_scenario_summary", {"scenario_id": scenario_id})
    top = ", ".join(f"{p['province']} ({p['exposed_population']:,})" for p in summary["most_exposed"][:3])
    text = (
        f"Under the {summary['scenario']['name']} scenario, {summary['exposed_population']:,} of "
        f"{summary['total_population']:,} people ({summary['exposed_share_pct']}%) live in flood-prone areas. "
        f"The most exposed provinces are {top}."
    )
    if compare_to:
        cmp = run_tool(conn, "compare_scenarios", {"base_scenario_id": compare_to, "target_scenario_id": scenario_id})
        direction = "more" if cmp["change"] >= 0 else "fewer"
        text += (
            f" Compared with {repository.get_scenario(conn, compare_to)['name']}, that is "
            f"{abs(cmp['change']):,} {direction} people ({cmp['change_pct']}%), and "
            f"{cmp['provinces_changing_class']} provinces move to a different risk class."
        )
    return text + " Hazard figures are illustrative."


# ---------- LLM loop ----------

def _llm_answer(conn: Connection, question: str, context: str, evidence: list[str],
                tools_used: list[str], client_factory: Callable | None = None) -> str | None:
    settings = get_settings()
    if client_factory is None:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=60)
    else:
        client = client_factory()
    messages = [{"role": "user", "content": f"{context}\n\nQuestion: {question}"}]
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.beta.messages.create(
            model=settings.llm_model,
            max_tokens=2000,
            # Server-side refusal fallback: a policy decline is retried on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )
        if response.stop_reason in ("refusal", "max_tokens"):
            return None
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text").strip()
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            output = json.dumps(run_tool(conn, block.name, dict(block.input)), default=str)
            evidence.append(output)
            tools_used.append(block.name)
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
        messages.append({"role": "user", "content": results})
    return None


def explain(conn: Connection, scenario_id: str, question: str, compare_to: str | None = None,
            client_factory: Callable | None = None) -> dict:
    repository.get_scenario(conn, scenario_id)  # 404 early for unknown scenarios
    if compare_to:
        repository.get_scenario(conn, compare_to)
    context = f"The user is viewing scenario '{scenario_id}'" + (f", compared with '{compare_to}'." if compare_to else ".")
    evidence, tools_used = [question], []

    answer = None
    if get_settings().anthropic_api_key or client_factory:
        answer = _llm_answer(conn, question, context, evidence, tools_used, client_factory)

    if answer:
        bad = unsupported_numbers(answer, evidence)
        if not bad:
            return {"answer": answer, "mode": "llm", "tools_used": tools_used, "guard": {"passed": True, "unsupported_numbers": []}}
        fallback = template_explanation(conn, scenario_id, compare_to)
        return {"answer": fallback, "mode": "template", "tools_used": tools_used,
                "guard": {"passed": False, "unsupported_numbers": bad}}
    return {"answer": template_explanation(conn, scenario_id, compare_to), "mode": "template", "tools_used": tools_used,
            "guard": {"passed": True, "unsupported_numbers": []}}
