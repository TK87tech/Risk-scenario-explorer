"""Load provinces, population and illustrative scenario hazard into PostGIS. Safe to run repeatedly.

Inputs (in ../data, or DATA_DIR):
- provinces.geojson: geoBoundaries THA ADM1 (OpenStreetMap / Wambacher, ODbL 1.0)
- population.csv: province population, December 2024 estimates (rounded)
- scenarios.yaml: scenarios and ILLUSTRATIVE flood shares (not a real hazard assessment)
"""

import csv
import hashlib
import json
import os
import re
from pathlib import Path

import yaml
from sqlalchemy import text

from app.db import get_engine

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))


def province_name(raw: str) -> str:
    return re.sub(r"\s+Province$", "", raw.strip())


def default_share(name: str, low: float, high: float) -> float:
    """A stable pseudo-random base share per province, so the illustrative data is reproducible."""
    fraction = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return round(low + (high - low) * fraction, 4)


def load_inputs() -> tuple[list[dict], list[dict], dict]:
    population = {r["province"]: int(r["population"]) for r in csv.DictReader(open(DATA_DIR / "population.csv", encoding="utf-8"))}
    features = json.loads((DATA_DIR / "provinces.geojson").read_text(encoding="utf-8"))["features"]
    provinces = []
    for f in features:
        name = province_name(f["properties"]["shapeName"])
        if name not in population:
            raise ValueError(f"No population for province {name!r}")
        geom = f["geometry"]
        if geom["type"] == "Polygon":
            geom = {"type": "MultiPolygon", "coordinates": [geom["coordinates"]]}
        provinces.append({"name": name, "population": population[name], "geom": json.dumps(geom)})
    missing = set(population) - {p["name"] for p in provinces}
    if missing:
        raise ValueError(f"Population rows without a boundary: {sorted(missing)}")
    config = yaml.safe_load((DATA_DIR / "scenarios.yaml").read_text(encoding="utf-8"))
    return provinces, config["scenarios"], config


def hazard_share(name: str, multiplier: float, config: dict) -> float:
    base = config["base_share"].get(name) or default_share(name, config["default_min"], config["default_max"])
    return round(min(base * multiplier, config["max_share"]), 4)


def seed() -> None:
    provinces, scenarios, config = load_inputs()
    with get_engine().begin() as conn:
        for p in provinces:
            conn.execute(
                text("""INSERT INTO provinces (name, population, geom)
                        VALUES (:name, :population, ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326))
                        ON CONFLICT (name) DO UPDATE SET population = EXCLUDED.population, geom = EXCLUDED.geom"""),
                p,
            )
        for s in scenarios:
            conn.execute(
                text("""INSERT INTO scenarios (id, name, description, multiplier)
                        VALUES (:id, :name, :description, :multiplier)
                        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description,
                            multiplier = EXCLUDED.multiplier"""),
                s,
            )
        ids = dict(conn.execute(text("SELECT name, id FROM provinces")).all())
        for s in scenarios:
            for p in provinces:
                conn.execute(
                    text("""INSERT INTO hazard (province_id, scenario_id, flood_share) VALUES (:pid, :sid, :share)
                            ON CONFLICT (province_id, scenario_id) DO UPDATE SET flood_share = EXCLUDED.flood_share"""),
                    {"pid": ids[p["name"]], "sid": s["id"], "share": hazard_share(p["name"], s["multiplier"], config)},
                )
    print(f"Seeded {len(provinces)} provinces and {len(scenarios)} scenarios.")


if __name__ == "__main__":
    seed()
