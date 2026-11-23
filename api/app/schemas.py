import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


def pace_min_per_km(distance_km: float, duration_seconds: int) -> float:
    """Ritmo en minutos por km (decimal). Ej: 5.5 = 5:30 min/km."""
    return round(duration_seconds / 60 / distance_km, 2)


def format_pace(distance_km: float, duration_seconds: int) -> str:
    """Ritmo como texto 'M:SS' (lo que usa cualquier runner)."""
    seconds_per_km = round(duration_seconds / distance_km)
    return f"{seconds_per_km // 60}:{seconds_per_km % 60:02d}"


class RunCreate(BaseModel):
    date: dt.date
    distance_km: float = Field(gt=0, le=500, description="Distancia en km")
    duration_seconds: int = Field(gt=0, le=7 * 24 * 3600, description="Duración en segundos")
    notes: str = Field(default="", max_length=500)


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: dt.date
    distance_km: float
    duration_seconds: int
    notes: str
    pace_min_per_km: float
    pace: str

    @classmethod
    def from_model(cls, run) -> "RunOut":
        return cls(
            id=run.id,
            date=run.date,
            distance_km=run.distance_km,
            duration_seconds=run.duration_seconds,
            notes=run.notes,
            pace_min_per_km=pace_min_per_km(run.distance_km, run.duration_seconds),
            pace=format_pace(run.distance_km, run.duration_seconds),
        )


class StatsOut(BaseModel):
    total_km: float
    total_runs: int
    # Ritmo promedio ponderado: tiempo total / km totales (no el promedio de
    # los ritmos, que sobrevaloraría las salidas cortas).
    avg_pace_min_per_km: float | None
    avg_pace: str | None
    longest_run: RunOut | None


class HealthOut(BaseModel):
    status: str
    database: str
