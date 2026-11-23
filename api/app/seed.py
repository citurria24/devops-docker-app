"""Datos de ejemplo para que la app no arranque vacía."""

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Run


def sample_runs(today: dt.date) -> list[Run]:
    def days_ago(n: int) -> dt.date:
        return today - dt.timedelta(days=n)

    # (días atrás, km, minutos, segundos, notas)
    data = [
        (13, 5.0, 28, 30, "Rodaje suave"),
        (10, 8.2, 45, 10, "Fondo corto por el parque"),
        (7, 6.0, 31, 45, "Series 6x400"),
        (4, 12.5, 72, 5, "Fondo largo del domingo"),
        (1, 4.3, 24, 0, "Regenerativo"),
    ]
    return [
        Run(date=days_ago(d), distance_km=km, duration_seconds=m * 60 + s, notes=notes)
        for d, km, m, s, notes in data
    ]


def seed_if_empty(db: Session) -> int:
    """Inserta los datos de ejemplo solo si la tabla está vacía.

    Devuelve cuántas filas insertó. Es idempotente: reiniciar el contenedor
    no duplica los datos.
    """
    count = db.scalar(select(func.count()).select_from(Run))
    if count:
        return 0
    runs = sample_runs(dt.date.today())
    db.add_all(runs)
    db.commit()
    return len(runs)
