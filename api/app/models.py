import datetime as dt

from sqlalchemy import Date, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    # La duración se guarda en segundos (entero) para evitar problemas de
    # redondeo; el ritmo se calcula al vuelo y no se persiste.
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str] = mapped_column(String(500), nullable=False, default="")
