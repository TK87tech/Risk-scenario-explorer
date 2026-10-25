"""Shared fixtures: a tiny fixed dataset instead of PostGIS, so unit and API tests run anywhere."""

import pytest

from app import repository
from app.risk import HazardRow

SCENARIOS = {
    "rp50": {"id": "rp50", "name": "50-year flood", "description": "2% annual chance"},
    "rp100": {"id": "rp100", "name": "100-year flood", "description": "1% annual chance"},
}
HAZARD = {
    "rp50": [HazardRow("Ayutthaya", 800_000, 0.40), HazardRow("Bangkok", 5_000_000, 0.18), HazardRow("Phuket", 400_000, 0.04)],
    "rp100": [HazardRow("Ayutthaya", 800_000, 0.52), HazardRow("Bangkok", 5_000_000, 0.234), HazardRow("Phuket", 400_000, 0.052)],
}


@pytest.fixture
def fake_repo(monkeypatch):
    def get_scenario(_conn, scenario_id):
        if scenario_id not in SCENARIOS:
            raise repository.NotFound(f"Unknown scenario: {scenario_id}")
        return SCENARIOS[scenario_id]

    def hazard_rows(conn, scenario_id):
        get_scenario(conn, scenario_id)
        return HAZARD[scenario_id]

    monkeypatch.setattr(repository, "get_scenario", get_scenario)
    monkeypatch.setattr(repository, "hazard_rows", hazard_rows)
    monkeypatch.setattr(repository, "list_scenarios", lambda _c: list(SCENARIOS.values()))
    monkeypatch.setattr(repository, "provinces_geojson", lambda _c, tolerance=0.005: {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"province": h.province}, "geometry": None} for h in HAZARD["rp50"]],
    })
