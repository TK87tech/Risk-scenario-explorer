"""Provinces, scenarios and hazard tables.

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("""
        CREATE TABLE provinces (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            population  INTEGER NOT NULL CHECK (population >= 0),
            geom        geometry(MultiPolygon, 4326) NOT NULL
        )""")
    op.execute("CREATE INDEX provinces_geom_idx ON provinces USING GIST (geom)")
    op.execute("""
        CREATE TABLE scenarios (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            description TEXT NOT NULL,
            multiplier  DOUBLE PRECISION NOT NULL CHECK (multiplier > 0)
        )""")
    op.execute("""
        CREATE TABLE hazard (
            province_id INTEGER NOT NULL REFERENCES provinces(id) ON DELETE CASCADE,
            scenario_id TEXT NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
            flood_share DOUBLE PRECISION NOT NULL CHECK (flood_share >= 0 AND flood_share <= 1),
            PRIMARY KEY (province_id, scenario_id)
        )""")


def downgrade() -> None:
    op.execute("DROP TABLE hazard")
    op.execute("DROP TABLE scenarios")
    op.execute("DROP TABLE provinces")
