"""API behaviour, including access control: public reads, signed-in explain, analyst-only downloads."""

import pytest
from fastapi.testclient import TestClient

from app.auth import User, current_user
from app.db import get_conn
from app.main import app


@pytest.fixture
def client(fake_repo):
    app.dependency_overrides[get_conn] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def sign_in(*roles):
    app.dependency_overrides[current_user] = lambda: User(subject="u1", username="tester", roles=frozenset(roles))


def test_public_results(client):
    r = client.get("/api/scenarios/rp50/results")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["exposed_population"] == 1_236_000
    assert body["provinces"][0]["province"] == "Bangkok"


def test_unknown_scenario_is_404(client):
    assert client.get("/api/scenarios/nope/results").status_code == 404


def test_compare(client):
    r = client.get("/api/compare", params={"base": "rp50", "target": "rp100"})
    assert r.status_code == 200 and r.json()["change"] == 370_800


def test_explain_requires_sign_in(client):
    assert client.post("/api/explain", json={"scenario_id": "rp50", "question": "Why?"}).status_code == 401


def test_explain_signed_in_uses_template_without_key(client):
    sign_in("viewer")
    r = client.post("/api/explain", json={"scenario_id": "rp100", "question": "How many people are exposed?"})
    assert r.status_code == 200 and "1,606,800" in r.json()["answer"]


def test_download_requires_sign_in(client):
    assert client.get("/api/scenarios/rp50/download").status_code == 401


def test_download_requires_analyst_role(client):
    sign_in("viewer")
    assert client.get("/api/scenarios/rp50/download").status_code == 403


def test_analyst_can_download_csv(client):
    sign_in("viewer", "analyst")
    r = client.get("/api/scenarios/rp50/download", params={"format": "csv"})
    assert r.status_code == 200
    assert r.text.splitlines()[0] == "province,population,exposed_population,exposed_share_pct,risk_class"


def test_explain_validates_input(client):
    sign_in("viewer")
    assert client.post("/api/explain", json={"scenario_id": "rp50", "question": "x" * 600}).status_code == 422
