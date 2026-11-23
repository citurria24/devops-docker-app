"""Conexión a la base de datos.

La URL sale de la variable de entorno DATABASE_URL. Si no está definida se usa
un archivo SQLite local (runlog.db), así la app se puede probar sin Postgres.

Ejemplo para Postgres:
    DATABASE_URL=postgresql+psycopg://runlog:secreto@db:5432/runlog
"""

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

DEFAULT_DATABASE_URL = "sqlite:///./runlog.db"


def normalize_url(url: str) -> str:
    """Fuerza el driver psycopg (v3) para URLs de Postgres.

    SQLAlchemy interpreta 'postgresql://' como psycopg2, que no instalamos.
    Así se puede usar tanto 'postgresql://' como 'postgres://' en el .env.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str) -> Engine:
    url = normalize_url(url)
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        # SQLite en memoria: cada conexión nueva sería una base distinta y vacía.
        # StaticPool reutiliza una única conexión (lo usan los tests).
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    # pool_pre_ping descarta conexiones muertas (por ejemplo, si se reinició la db).
    return create_engine(url, pool_pre_ping=True)


DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por request, siempre cerrada al final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
