"""MCP server exposing Risk Scenario Explorer results as tools.

It calls the API rather than recalculating, so every client (the web app, this MCP server, the LLM explainer)
gets numbers from one source. Run it over stdio for local MCP clients (Claude Code, Cursor, Codex, OpenCode), or
over Streamable HTTP with MCP_TRANSPORT=streamable-http.
"""

import os

import httpx
from mcp.server.mcpserver import MCPServer

API = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

mcp = MCPServer(
    "risk-scenario-explorer",
    instructions="Flood-exposure results for Thai provinces. Numbers come from the API; hazard data is illustrative.",
)


def _get(path: str, **params) -> dict | list:
    resp = httpx.get(f"{API}{path}", params=params, timeout=30)
    if resp.status_code == 404:
        return {"error": resp.json().get("detail", "not found")}
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
def list_scenarios() -> list | dict:
    """List the available flood scenarios (id, name, description)."""
    return _get("/api/scenarios")


@mcp.tool()
def get_scenario_summary(scenario_id: str) -> dict:
    """Totals for one scenario: total and exposed population, exposed share, provinces per risk class and the
    five most exposed provinces. scenario_id is e.g. rp10, rp50, rp100 or rp100_2050."""
    data = _get(f"/api/scenarios/{scenario_id}/results")
    return data if "error" in data else {"scenario": data["scenario"], **data["summary"]}


@mcp.tool()
def get_province_result(scenario_id: str, province: str) -> dict:
    """Exposed population, exposed share and risk class for one Thai province under one scenario."""
    data = _get(f"/api/scenarios/{scenario_id}/results")
    if "error" in data:
        return data
    match = next((p for p in data["provinces"] if p["province"].lower() == province.strip().lower()), None)
    return match or {"error": f"No province named {province!r}", "provinces": [p["province"] for p in data["provinces"]]}


@mcp.tool()
def compare_scenarios(base_scenario_id: str, target_scenario_id: str) -> dict:
    """Change in exposed population from a base to a target scenario, with the provinces whose exposure grows most."""
    data = _get("/api/compare", base=base_scenario_id, target=target_scenario_id)
    if isinstance(data, dict):
        data.pop("all", None)
    return data


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.run("streamable-http", host=os.getenv("MCP_HOST", "127.0.0.1"), port=int(os.getenv("MCP_PORT", "8001")))
    else:
        mcp.run("stdio")
