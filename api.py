"""Read-only REST API for the future Android client."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import yaml
from fastapi import Body, FastAPI, HTTPException, Query, Response

from modules.database import Database
from modules.repository import StockRepository
from modules.screener import Screener
from modules.sector import SectorAnalyzer
from modules.portfolio import PortfolioAnalyzer
from modules.health import HealthChecker
from modules.reporting import DailyReportBuilder
from modules.chart import StockChartRenderer
from modules.screening_options import ScreeningOptions

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="StockAI Navigator API", version="0.1.0")

def settings() -> dict:
    with (ROOT / "config" / "settings.yaml").open(encoding="utf-8") as file:
        return yaml.safe_load(file)

def repository() -> tuple[sqlite3.Connection, StockRepository]:
    db = Database(ROOT / settings()["database"]["path"])
    db.initialize()
    connection = sqlite3.connect(db.path)
    connection.row_factory = sqlite3.Row
    return connection, StockRepository(connection)

def load_config(name: str) -> dict:
    with (ROOT / "config" / name).open(encoding="utf-8") as file:
        return yaml.safe_load(file)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/system/health")
def system_health() -> dict:
    db = Database(ROOT / settings()["database"]["path"])
    db.initialize()
    with db.connect() as connection:
        return HealthChecker(connection).report()

@app.get("/reports/daily")
def daily_report() -> dict:
    """Return the current local summary without creating a report file."""
    db = Database(ROOT / settings()["database"]["path"])
    db.initialize()
    with db.connect() as connection:
        return DailyReportBuilder(connection).build()

@app.get("/stocks/{code}/overview")
def stock_overview(code: str) -> dict:
    connection, repo = repository()
    try:
        indices = settings().get("market_indices", [])
        benchmark_code = indices[0].get("code") if isinstance(indices, list) and indices and isinstance(indices[0], dict) else None
        result = repo.overview(code, benchmark_code)
    finally:
        connection.close()
    if result is None:
        raise HTTPException(status_code=404, detail="No stored data found for this code")
    return result

@app.get("/stocks/{code}/prices")
def prices(code: str, timeframe: str = "daily", limit: int = Query(default=300, ge=1, le=5000)) -> dict:
    connection, repo = repository()
    try:
        values = repo.prices(code, timeframe, limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        connection.close()
    if not values:
        raise HTTPException(status_code=404, detail="No prices found for this code")
    return {"code": code, "timeframe": timeframe, "prices": values}

@app.get("/stocks/{code}/chart.svg")
def chart_svg(code: str) -> Response:
    """Render a local SVG chart; it is not published outside this API."""
    connection, repo = repository()
    try:
        values = repo.prices(code, "daily", limit=180)
        overview = repo.overview(code)
    finally:
        connection.close()
    if not values:
        raise HTTPException(status_code=404, detail="No prices found for this code")
    company_name = (overview or {}).get("master", {}).get("company_name") if (overview or {}).get("master") else None
    return Response(StockChartRenderer.render(code, values, company_name), media_type="image/svg+xml")

@app.get("/stocks/{code}/history")
def history(code: str, limit: int = Query(default=100, ge=1, le=1000)) -> dict:
    connection, repo = repository()
    try:
        return {"code": code, "history": repo.analysis_history(code, limit)}
    finally:
        connection.close()

@app.get("/rankings")
def rankings(limit: int = Query(default=100, ge=1, le=1000)) -> dict:
    connection, repo = repository()
    try:
        return {"rankings": repo.latest_rankings(limit)}
    finally:
        connection.close()

@app.get("/rankings/changes")
def ranking_changes(
    limit: int = Query(default=100, ge=1, le=1000),
    minimum_delta: float = Query(default=0.0, ge=0.0),
) -> dict:
    connection, repo = repository()
    try:
        return {"changes": repo.score_changes(limit, minimum_delta)}
    finally:
        connection.close()

@app.get("/jobs")
def jobs(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    connection, repo = repository()
    try:
        return {"jobs": repo.recent_jobs(limit)}
    finally:
        connection.close()

@app.get("/watchlist")
def watchlist() -> dict:
    db = Database(ROOT / settings()["database"]["path"])
    db.initialize()
    with db.connect() as connection:
        rows = connection.execute(
            """SELECT w.code, w.note, w.created_at, m.company_name, m.sector_33_name
               FROM watchlist w LEFT JOIN master_stock m ON m.code=w.code ORDER BY w.created_at DESC"""
        ).fetchall()
    return {"watchlist": [dict(row) for row in rows]}

@app.get("/portfolio")
def portfolio() -> dict:
    db = Database(ROOT / settings()["database"]["path"])
    db.initialize()
    with db.connect() as connection:
        return PortfolioAnalyzer(connection).positions()

@app.get("/screening-options")
def screening_options() -> dict:
    return ScreeningOptions(load_config("screening_options.yaml"), load_config("screening.yaml")).catalog()

@app.post("/screening-preview")
def screening_preview(payload: dict = Body(...)) -> dict:
    """Preview bounded manual conditions without persisting or changing cloud settings."""
    options = ScreeningOptions(load_config("screening_options.yaml"), load_config("screening.yaml"))
    try:
        rule = options.manual_rule(payload.get("conditions") or [], str(payload.get("logic") or "all"))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    indicator_config = load_config("indicators.yaml")
    manual_config = {"active_profile": "manual_preview", "profiles": {"manual_preview": rule}}
    db = Database(ROOT / settings()["database"]["path"])
    db.initialize()
    with db.connect() as connection:
        hits = Screener(connection, indicator_config, manual_config).run("manual_preview")
    return {"mode": "manual", "persisted": False, "rule": rule, "hit_count": len(hits), "hits": hits}

@app.get("/screening/{profile_name}")
def screening(profile_name: str) -> dict:
    with (ROOT / "config" / "indicators.yaml").open(encoding="utf-8") as file:
        indicator_config = yaml.safe_load(file)
    with (ROOT / "config" / "screening.yaml").open(encoding="utf-8") as file:
        screening_config = yaml.safe_load(file)
    if profile_name not in screening_config["profiles"]:
        raise HTTPException(status_code=404, detail="Unknown profile")
    db = Database(ROOT / settings()["database"]["path"])
    db.initialize()
    with db.connect() as connection:
        hits = Screener(connection, indicator_config, screening_config).run(profile_name)
    return {"profile": profile_name, "hits": hits}

@app.get("/screening/{profile_name}/sectors")
def screening_sectors(profile_name: str) -> dict:
    with (ROOT / "config" / "indicators.yaml").open(encoding="utf-8") as file:
        indicator_config = yaml.safe_load(file)
    with (ROOT / "config" / "screening.yaml").open(encoding="utf-8") as file:
        screening_config = yaml.safe_load(file)
    if profile_name not in screening_config["profiles"]:
        raise HTTPException(status_code=404, detail="Unknown profile")
    db = Database(ROOT / settings()["database"]["path"])
    db.initialize()
    with db.connect() as connection:
        hits = Screener(connection, indicator_config, screening_config).run(profile_name)
        sectors = SectorAnalyzer(connection).summarize_hits(hits)
    return {"profile": profile_name, "hit_count": len(hits), "sectors": sectors}
