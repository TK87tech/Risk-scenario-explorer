"""Deterministic risk calculations: the single source of calculated results.

The API, the MCP server and the LLM explanations all get their numbers from these functions. The language model
never calculates anything; it only explains what these return.
"""

from dataclasses import asdict, dataclass

RISK_CLASSES = [(0.05, "low"), (0.15, "moderate"), (0.30, "high"), (1.01, "very high")]


@dataclass(frozen=True)
class HazardRow:
    province: str
    population: int
    flood_share: float  # share of population in flood-prone areas for the scenario, 0-1


@dataclass(frozen=True)
class ProvinceResult:
    province: str
    population: int
    exposed_population: int
    exposed_share_pct: float
    risk_class: str


def risk_class(share: float) -> str:
    return next(label for limit, label in RISK_CLASSES if share < limit)


def province_results(rows: list[HazardRow]) -> list[ProvinceResult]:
    """Exposed population per province, sorted from most to least exposed."""
    results = [
        ProvinceResult(
            province=r.province,
            population=r.population,
            exposed_population=round(r.population * r.flood_share),
            exposed_share_pct=round(r.flood_share * 100, 1),
            risk_class=risk_class(r.flood_share),
        )
        for r in rows
    ]
    return sorted(results, key=lambda p: (-p.exposed_population, p.province))


def summarize(results: list[ProvinceResult], top: int = 5) -> dict:
    total_pop = sum(r.population for r in results)
    exposed = sum(r.exposed_population for r in results)
    by_class = {label: 0 for _, label in RISK_CLASSES}
    for r in results:
        by_class[r.risk_class] += 1
    return {
        "provinces": len(results),
        "total_population": total_pop,
        "exposed_population": exposed,
        "exposed_share_pct": round(exposed / total_pop * 100, 1) if total_pop else 0.0,
        "provinces_by_risk_class": by_class,
        "most_exposed": [asdict(r) for r in results[:top]],
    }


def compare(base: list[ProvinceResult], target: list[ProvinceResult], top: int = 5) -> dict:
    """Change in exposure from the base scenario to the target scenario."""
    base_by_name = {r.province: r for r in base}
    changes = []
    for t in target:
        b = base_by_name[t.province]
        changes.append({
            "province": t.province,
            "base_exposed": b.exposed_population,
            "target_exposed": t.exposed_population,
            "change": t.exposed_population - b.exposed_population,
            "base_risk_class": b.risk_class,
            "target_risk_class": t.risk_class,
        })
    changes.sort(key=lambda c: (-c["change"], c["province"]))
    base_total = sum(r.exposed_population for r in base)
    target_total = sum(r.exposed_population for r in target)
    return {
        "base_exposed_population": base_total,
        "target_exposed_population": target_total,
        "change": target_total - base_total,
        "change_pct": round((target_total - base_total) / base_total * 100, 1) if base_total else 0.0,
        "provinces_changing_class": sum(c["base_risk_class"] != c["target_risk_class"] for c in changes),
        "largest_increases": changes[:top],
        "all": changes,
    }
