from app import risk
from tests.conftest import HAZARD


def test_exposed_population_and_class():
    results = risk.province_results(HAZARD["rp50"])
    assert [r.province for r in results] == ["Bangkok", "Ayutthaya", "Phuket"]  # most exposed first
    bkk = results[0]
    assert bkk.exposed_population == 900_000
    assert bkk.exposed_share_pct == 18.0
    assert bkk.risk_class == "high"
    assert results[2].risk_class == "low"


def test_risk_class_boundaries():
    assert risk.risk_class(0.0) == "low"
    assert risk.risk_class(0.05) == "moderate"
    assert risk.risk_class(0.15) == "high"
    assert risk.risk_class(0.30) == "very high"
    assert risk.risk_class(1.0) == "very high"


def test_summary_totals():
    summary = risk.summarize(risk.province_results(HAZARD["rp50"]))
    assert summary["total_population"] == 6_200_000
    assert summary["exposed_population"] == 320_000 + 900_000 + 16_000
    assert summary["exposed_share_pct"] == 19.9
    assert summary["provinces_by_risk_class"] == {"low": 1, "moderate": 0, "high": 1, "very high": 1}


def test_compare_scenarios():
    base = risk.province_results(HAZARD["rp50"])
    target = risk.province_results(HAZARD["rp100"])
    result = risk.compare(base, target)
    assert result["base_exposed_population"] == 1_236_000
    assert result["target_exposed_population"] == 416_000 + 1_170_000 + 20_800
    assert result["change"] == result["target_exposed_population"] - result["base_exposed_population"]
    assert result["largest_increases"][0]["province"] == "Bangkok"
    assert result["provinces_changing_class"] == 1  # only Phuket: 4% (low) -> 5.2% (moderate)
