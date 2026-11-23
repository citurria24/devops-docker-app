import os

# Hay que definir el entorno ANTES de importar la app, porque el engine se crea
# al importar app.database. SQLite en memoria: no hace falta Postgres en CI.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SEED_SAMPLE_DATA"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    # Base limpia en cada test para que no dependan unos de otros.
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as c:  # el "with" ejecuta el lifespan (crea tablas)
        yield c
    app.dependency_overrides.clear()
