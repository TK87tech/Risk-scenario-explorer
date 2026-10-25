import csv
import io
import json
import logging
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app import repository, risk
from app.auth import User, current_user, require_role
from app.config import get_settings
from app.db import get_conn
from app.explain import explain

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("grp.api")

app = FastAPI(
    title="Risk Scenario Explorer API",
    description="Deterministic flood-exposure results per province and scenario. Hazard data is illustrative.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(repository.NotFound)
def not_found(_: Request, exc: repository.NotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


# ---------- health ----------

@app.get("/health", tags=["ops"])
def health() -> dict:
    """Liveness: the process is up."""
    return {"status": "ok"}


@app.get("/ready", tags=["ops"])
def ready(conn: Connection = Depends(get_conn)) -> dict:
    """Readiness: the database is reachable and seeded."""
    count = conn.execute(text("SELECT COUNT(*) FROM provinces")).scalar_one()
    if count == 0:
        raise HTTPException(503, "Database not seeded")
    return {"status": "ready", "provinces": count}


# ---------- public, read-only ----------

@app.get("/api/scenarios", tags=["results"])
def scenarios(conn: Connection = Depends(get_conn)) -> list[dict]:
    return repository.list_scenarios(conn)


@app.get("/api/provinces", tags=["results"])
def provinces(conn: Connection = Depends(get_conn)) -> dict:
    """Province outlines as GeoJSON (simplified)."""
    return repository.provinces_geojson(conn)


@app.get("/api/scenarios/{scenario_id}/results", tags=["results"])
def results(scenario_id: str, conn: Connection = Depends(get_conn)) -> dict:
    rows = risk.province_results(repository.hazard_rows(conn, scenario_id))
    return {"scenario": repository.get_scenario(conn, scenario_id), "summary": risk.summarize(rows),
            "provinces": [r.__dict__ for r in rows]}


@app.get("/api/compare", tags=["results"])
def compare(base: str = Query(..., description="Base scenario id"), target: str = Query(..., description="Target scenario id"),
            conn: Connection = Depends(get_conn)) -> dict:
    b = risk.province_results(repository.hazard_rows(conn, base))
    t = risk.province_results(repository.hazard_rows(conn, target))
    return {"base": repository.get_scenario(conn, base), "target": repository.get_scenario(conn, target), **risk.compare(b, t)}


# ---------- signed-in users ----------

class ExplainRequest(BaseModel):
    scenario_id: str = Field(max_length=40)
    compare_to: str | None = Field(default=None, max_length=40)
    question: str = Field(min_length=3, max_length=500)


@app.post("/api/explain", tags=["ai"])
def explain_results(body: ExplainRequest, user: User = Depends(current_user),
                    conn: Connection = Depends(get_conn)) -> dict:
    """Plain-English explanation of results. Numbers come only from the deterministic tools (see app/explain.py)."""
    result = explain(conn, body.scenario_id, body.question, body.compare_to)
    log.info("explain user=%s scenario=%s mode=%s guard_passed=%s", user.subject, body.scenario_id,
             result["mode"], result["guard"]["passed"])
    return result


# ---------- analysts only ----------

@app.get("/api/scenarios/{scenario_id}/download", tags=["results"])
def download(scenario_id: str, format: Literal["csv", "geojson"] = "csv",
             user: User = Depends(require_role("analyst")), conn: Connection = Depends(get_conn)) -> Response:
    rows = risk.province_results(repository.hazard_rows(conn, scenario_id))
    log.info("download user=%s scenario=%s format=%s", user.subject, scenario_id, format)
    if format == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].__dict__))
        writer.writeheader()
        writer.writerows(r.__dict__ for r in rows)
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{scenario_id}_results.csv"'})
    by_name = {r.province: r.__dict__ for r in rows}
    geo = repository.provinces_geojson(conn)
    for f in geo["features"]:
        f["properties"].update(by_name[f["properties"]["province"]])
    return Response(json.dumps(geo), media_type="application/geo+json",
                    headers={"Content-Disposition": f'attachment; filename="{scenario_id}_results.geojson"'})
