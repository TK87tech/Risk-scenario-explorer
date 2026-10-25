"""Read-only queries. Business logic lives in risk.py; this module only fetches inputs."""

import json

from sqlalchemy import Connection, text

from app.risk import HazardRow


class NotFound(Exception):
    pass


def list_scenarios(conn: Connection) -> list[dict]:
    rows = conn.execute(text("SELECT id, name, description FROM scenarios ORDER BY multiplier")).mappings()
    return [dict(r) for r in rows]


def get_scenario(conn: Connection, scenario_id: str) -> dict:
    row = conn.execute(
        text("SELECT id, name, description FROM scenarios WHERE id = :id"), {"id": scenario_id}
    ).mappings().first()
    if row is None:
        raise NotFound(f"Unknown scenario: {scenario_id}")
    return dict(row)


def hazard_rows(conn: Connection, scenario_id: str) -> list[HazardRow]:
    get_scenario(conn, scenario_id)
    rows = conn.execute(
        text("""SELECT p.name, p.population, h.flood_share
                FROM hazard h JOIN provinces p ON p.id = h.province_id
                WHERE h.scenario_id = :id ORDER BY p.name"""),
        {"id": scenario_id},
    )
    return [HazardRow(province=r[0], population=r[1], flood_share=r[2]) for r in rows]


def provinces_geojson(conn: Connection, tolerance: float = 0.005) -> dict:
    """Province outlines, simplified in PostGIS so the browser downloads less."""
    rows = conn.execute(
        text("""SELECT name, ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, :tol), 4) AS geometry
                FROM provinces ORDER BY name"""),
        {"tol": tolerance},
    )
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"province": r[0]}, "geometry": json.loads(r[1])} for r in rows
        ],
    }
