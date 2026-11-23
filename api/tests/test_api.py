import datetime as dt

import pytest

from app.database import SessionLocal, get_db
from app.main import app
from app.schemas import format_pace, pace_min_per_km
from app.seed import seed_if_empty


def make_run(client, **overrides):
    payload = {
        "date": "2026-11-01",
        "distance_km": 10.0,
        "duration_seconds": 50 * 60,
        "notes": "test",
    }
    payload.update(overrides)
    resp = client.post("/api/runs", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- health -----------------------------------------------------------------

def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


def test_health_returns_503_when_db_fails(client):
    class BrokenSession:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("db caída")

    app.dependency_overrides[get_db] = lambda: BrokenSession()
    resp = client.get("/api/health")
    assert resp.status_code == 503
    assert resp.json()["database"] == "unreachable"


# --- crear / listar / borrar ------------------------------------------------

def test_create_run(client):
    run = make_run(client, notes="Fondo")
    assert run["id"] > 0
    assert run["distance_km"] == 10.0
    assert run["notes"] == "Fondo"
    assert run["pace"] == "5:00"


@pytest.mark.parametrize(
    "bad",
    [
        {"distance_km": 0},
        {"distance_km": -3},
        {"duration_seconds": 0},
        {"date": "no-es-fecha"},
    ],
)
def test_create_run_validation(client, bad):
    payload = {"date": "2026-11-01", "distance_km": 5, "duration_seconds": 1500, **bad}
    assert client.post("/api/runs", json=payload).status_code == 422


def test_list_runs_newest_first(client):
    make_run(client, date="2026-10-01")
    make_run(client, date="2026-11-01")
    runs = client.get("/api/runs").json()
    assert [r["date"] for r in runs] == ["2026-11-01", "2026-10-01"]


def test_delete_run(client):
    run = make_run(client)
    assert client.delete(f"/api/runs/{run['id']}").status_code == 204
    assert client.get("/api/runs").json() == []


def test_delete_missing_run_returns_404(client):
    assert client.delete("/api/runs/9999").status_code == 404


# --- cálculo de ritmo -------------------------------------------------------

@pytest.mark.parametrize(
    ("km", "seconds", "decimal", "text"),
    [
        (10, 50 * 60, 5.0, "5:00"),
        (5, 27 * 60 + 30, 5.5, "5:30"),
        (21.0975, 7200, 5.69, "5:41"),  # media maratón en 2 h
        (1, 59, 0.98, "0:59"),
    ],
)
def test_pace_calculation(km, seconds, decimal, text):
    assert pace_min_per_km(km, seconds) == decimal
    assert format_pace(km, seconds) == text


# --- stats ------------------------------------------------------------------

def test_stats_empty(client):
    assert client.get("/api/stats").json() == {
        "total_km": 0.0,
        "total_runs": 0,
        "avg_pace_min_per_km": None,
        "avg_pace": None,
        "longest_run": None,
    }


def test_stats(client):
    make_run(client, distance_km=5, duration_seconds=30 * 60)  # 6:00/km
    longest = make_run(client, distance_km=15, duration_seconds=75 * 60)  # 5:00/km
    stats = client.get("/api/stats").json()
    assert stats["total_km"] == 20.0
    assert stats["total_runs"] == 2
    # Ponderado por distancia: 105 min / 20 km = 5.25 -> 5:15 (no 5:30).
    assert stats["avg_pace_min_per_km"] == 5.25
    assert stats["avg_pace"] == "5:15"
    assert stats["longest_run"]["id"] == longest["id"]


# --- datos de ejemplo -------------------------------------------------------

def test_seed_only_when_empty(client):
    with SessionLocal() as db:
        assert seed_if_empty(db) > 0
        assert seed_if_empty(db) == 0  # segunda vez no duplica
    runs = client.get("/api/runs").json()
    assert all(dt.date.fromisoformat(r["date"]) <= dt.date.today() for r in runs)
