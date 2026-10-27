"""Bounded-LLM behaviour: reference questions, the number guard, and fake models (no API key or network needed)."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from app import explain as ex

REFERENCE = yaml.safe_load((Path(__file__).parent / "reference_questions.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", REFERENCE, ids=[c["question"] for c in REFERENCE])
def test_reference_questions_template(fake_repo, case):
    result = ex.explain(None, case["scenario_id"], case["question"], case.get("compare_to"))
    assert result["mode"] == "template"
    for expected in case["expect_numbers"]:
        assert expected in result["answer"], f"{expected} missing from: {result['answer']}"


def test_guard_accepts_numbers_from_tools():
    evidence = ['{"exposed_population": 1606800, "exposed_share_pct": 25.9}']
    assert ex.unsupported_numbers("1,606,800 people (25.9%) are exposed.", evidence) == []


def test_guard_rejects_invented_numbers():
    evidence = ['{"exposed_population": 1606800}']
    assert ex.unsupported_numbers("About 1.6 million people, or 26%, are exposed.", evidence) == ["1.6", "26"]


# ---------- fake LLM clients ----------

def _block(**kw):
    return SimpleNamespace(**kw)


class FakeClient:
    """Plays back scripted responses: first a tool call, then a final text answer."""

    def __init__(self, final_text: str):
        self.calls = 0
        self.final_text = final_text
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return SimpleNamespace(stop_reason="tool_use", content=[
                _block(type="tool_use", id="t1", name="get_scenario_summary", input={"scenario_id": "rp100"})])
        return SimpleNamespace(stop_reason="end_turn", content=[_block(type="text", text=self.final_text)])


def test_llm_answer_grounded_in_tools_passes(fake_repo):
    client = FakeClient("Under the 100-year flood, 1,606,800 of 6,200,000 people (25.9%) are exposed.")
    result = ex.explain(None, "rp100", "How many people are exposed?", client_factory=lambda: client)
    assert result["mode"] == "llm"
    assert result["guard"]["passed"]
    assert result["tools_used"] == ["get_scenario_summary"]


def test_llm_answer_with_invented_number_falls_back(fake_repo):
    client = FakeClient("Roughly 1.7 million people are exposed.")
    result = ex.explain(None, "rp100", "How many people are exposed?", client_factory=lambda: client)
    assert result["mode"] == "template"
    assert not result["guard"]["passed"]
    assert result["guard"]["unsupported_numbers"] == ["1.7"]
    assert "1,606,800" in result["answer"]


def test_provider_error_falls_back_to_template(fake_repo):
    def failing_client():
        raise RuntimeError("429 Too Many Requests")

    result = ex.explain(None, "rp100", "How many people are exposed?", client_factory=failing_client)
    assert result["mode"] == "template"
    assert "1,606,800" in result["answer"]


# ---------- OpenRouter (OpenAI-compatible chat completions) ----------

@pytest.fixture
def openrouter(monkeypatch):
    settings = ex.get_settings().model_copy(update={"llm_provider": "openrouter"})
    monkeypatch.setattr(ex, "get_settings", lambda: settings)


class FakeChat:
    """Plays back OpenRouter responses: first a tool call, then a final text answer."""

    def __init__(self, final_text: str):
        self.payloads = []
        self.final_text = final_text

    def __call__(self, payload):
        self.payloads.append(payload)
        if len(self.payloads) == 1:
            call = {"id": "c1", "type": "function",
                    "function": {"name": "get_scenario_summary", "arguments": '{"scenario_id": "rp100"}'}}
            return {"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [call]}}]}
        return {"choices": [{"finish_reason": "stop", "message": {"content": self.final_text}}]}


def test_openrouter_answer_grounded_in_tools_passes(fake_repo, openrouter):
    chat = FakeChat("Under the 100-year flood, 1,606,800 of 6,200,000 people (25.9%) are exposed.")
    result = ex.explain(None, "rp100", "How many people are exposed?", client_factory=lambda: chat)
    assert result["mode"] == "llm"
    assert result["tools_used"] == ["get_scenario_summary"]
    assert chat.payloads[0]["tools"][0]["function"]["name"] == "get_scenario_summary"
    assert chat.payloads[1]["messages"][-1] == {"role": "tool", "tool_call_id": "c1", "content": ex.json.dumps(
        ex.run_tool(None, "get_scenario_summary", {"scenario_id": "rp100"}), default=str)}


def test_scenario_names_count_as_evidence(fake_repo):
    client = FakeClient("Under the 50-year flood, 1,606,800 people (25.9%) are exposed.")
    result = ex.explain(None, "rp50", "How many people are exposed?", client_factory=lambda: client)
    assert result["mode"] == "llm"


def test_openrouter_answer_with_invented_number_falls_back(fake_repo, openrouter):
    result = ex.explain(None, "rp100", "How many people are exposed?",
                        client_factory=lambda: FakeChat("Roughly 1.7 million people are exposed."))
    assert result["mode"] == "template"
    assert result["guard"]["unsupported_numbers"] == ["1.7"]


def test_unknown_province_is_reported_not_invented(fake_repo):
    out = ex.run_tool(None, "get_province_result", {"scenario_id": "rp50", "province": "Atlantis"})
    assert "error" in out and "Bangkok" in out["provinces"]
