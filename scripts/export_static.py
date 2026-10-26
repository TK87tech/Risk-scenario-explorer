"""Export a static data snapshot for the GitHub Pages demo (web/public/data/).

Every number comes from the same deterministic code the API uses (app.risk / app.explain), read from the seeded
PostGIS database, so the static demo shows exactly what the full stack returns.

    docker compose up -d db api        # database migrated and seeded
    cd api && python ../scripts/export_static.py
"""

import json
import sys
from itertools import permutations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from app import repository, risk  # noqa: E402
from app.db import get_engine  # noqa: E402
from app.explain import template_explanation  # noqa: E402

OUT = ROOT / "web" / "public" / "data"


def write(name: str, data) -> None:
    (OUT / name).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with get_engine().connect() as conn:
        scenarios = repository.list_scenarios(conn)
        write("scenarios.json", scenarios)
        write("provinces.json", repository.provinces_geojson(conn))
        results = {s["id"]: risk.province_results(repository.hazard_rows(conn, s["id"])) for s in scenarios}
        explanations = {}
        for s in scenarios:
            rows = results[s["id"]]
            write(f"results_{s['id']}.json",
                  {"scenario": s, "summary": risk.summarize(rows), "provinces": [r.__dict__ for r in rows]})
            explanations[s["id"]] = template_explanation(conn, s["id"], None)
        by_id = {s["id"]: s for s in scenarios}
        for base, target in permutations(by_id, 2):
            write(f"compare_{base}__{target}.json",
                  {"base": by_id[base], "target": by_id[target], **risk.compare(results[base], results[target])})
            explanations[f"{target}|{base}"] = template_explanation(conn, target, base)
        write("explanations.json", explanations)
    print(f"Exported {len(scenarios)} scenarios to {OUT}")


if __name__ == "__main__":
    main()
