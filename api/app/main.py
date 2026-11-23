"""RunLog API: registro de salidas a correr.

Arranque local:
    uvicorn app.main:app --reload --port 8000
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, get_db
from .models import Run
from .schemas import HealthOut, RunCreate, RunOut, StatsOut, format_pace, pace_min_per_km
from .seed import seed_if_empty

logger = logging.getLogger("runlog")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

# Reintentos al conectar en el arranque. Aunque compose espere a que la db esté
# "healthy", un pequeño margen evita que la api muera por una carrera puntual.
STARTUP_DB_RETRIES = 10
STARTUP_DB_RETRY_DELAY_SECONDS = 2


def init_db() -> None:
    """Crea las tablas (si no existen) y carga los datos de ejemplo."""
    for attempt in range(1, STARTUP_DB_RETRIES + 1):
        try:
            Base.metadata.create_all(bind=engine)
            break
        except OperationalError as exc:
            if attempt == STARTUP_DB_RETRIES:
                raise
            logger.warning(
                "La base no responde (intento %d/%d): %s",
                attempt, STARTUP_DB_RETRIES, exc.orig,
            )
            time.sleep(STARTUP_DB_RETRY_DELAY_SECONDS)

    if os.getenv("SEED_SAMPLE_DATA", "true").lower() in ("1", "true", "yes"):
        with SessionLocal() as db:
            inserted = seed_if_empty(db)
            if inserted:
                logger.info("Cargadas %d salidas de ejemplo", inserted)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield
    engine.dispose()


app = FastAPI(title="RunLog API", version="1.0.0", lifespan=lifespan)

# Sesión de base inyectada por FastAPI en cada endpoint (forma recomendada con Annotated).
DbSession = Annotated[Session, Depends(get_db)]


@app.get("/api/health", response_model=HealthOut, responses={503: {"model": HealthOut}})
def health(db: DbSession):
    """Healthcheck: comprueba que la api responde Y que la base está accesible.

    Devuelve 503 si la base no responde, para que Docker/compose marquen el
    contenedor como 'unhealthy'.
    """
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # cualquier fallo de la db = no saludable
        logger.error("Healthcheck: la base no responde: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "database": "unreachable"},
        )
    return HealthOut(status="ok", database="ok")


@app.get("/api/runs", response_model=list[RunOut])
def list_runs(db: DbSession):
    runs = db.scalars(select(Run).order_by(Run.date.desc(), Run.id.desc())).all()
    return [RunOut.from_model(r) for r in runs]


@app.post("/api/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def create_run(payload: RunCreate, db: DbSession):
    run = Run(**payload.model_dump())
    db.add(run)
    db.commit()
    db.refresh(run)
    return RunOut.from_model(run)


@app.delete("/api/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run(run_id: int, db: DbSession):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Salida no encontrada")
    db.delete(run)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/stats", response_model=StatsOut)
def stats(db: DbSession):
    total_runs, total_km, total_seconds = db.execute(
        select(
            func.count(Run.id),
            func.coalesce(func.sum(Run.distance_km), 0.0),
            func.coalesce(func.sum(Run.duration_seconds), 0),
        )
    ).one()
    longest = db.scalars(
        select(Run).order_by(Run.distance_km.desc(), Run.date.desc()).limit(1)
    ).first()

    has_data = total_runs > 0 and total_km > 0
    return StatsOut(
        total_km=round(total_km, 2),
        total_runs=total_runs,
        avg_pace_min_per_km=pace_min_per_km(total_km, total_seconds) if has_data else None,
        avg_pace=format_pace(total_km, total_seconds) if has_data else None,
        longest_run=RunOut.from_model(longest) if longest else None,
    )


# Solo para desarrollo local SIN Docker: si WEB_DIR apunta a la carpeta web/,
# la api sirve también el frontend en "/". En los contenedores esto lo hace
# nginx y WEB_DIR no se define. Se monta al final para no tapar las rutas /api.
_web_dir = os.getenv("WEB_DIR")
if _web_dir and Path(_web_dir).is_dir():
    app.mount("/", StaticFiles(directory=_web_dir, html=True), name="web")
