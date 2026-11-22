from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from math import log1p
from typing import TypeAlias

from app.core.clock import LIMA

Features: TypeAlias = dict[str, str | float | int]

FEATURE_SCHEMA = "2"
LOOKBACK_DAYS = 365
SEED = 42


@dataclass(frozen=True)
class Sample:
    moment: datetime
    features: Features
    label: int | None = None
    known_at: datetime | None = None
    subject: int | None = None


def calendar(day: date, hour: int, court: int, discipline: int) -> Features:
    return {
        "losa": str(court),
        "disciplina": str(discipline),
        "dia_semana": str(day.weekday()),
        "mes": str(day.month),
        "hora": hour,
    }


def no_show_features(
    day: date, start: time, court: int, discipline: int, duration: int, kind: str, confirmed: datetime
) -> Features:
    lead = (datetime.combine(day, start, LIMA) - confirmed).total_seconds() / 3600
    return {
        **calendar(day, start.hour, court, discipline),
        "duracion": duration,
        "tipo": kind,
        "anticipacion_log_horas": log1p(max(0, lead)),
    }


def hours(opening: time, closing: time) -> range:
    start = opening.hour + int(bool(opening.minute or opening.second or opening.microsecond))
    return range(start, closing.hour)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def utc_assumed(value: datetime) -> datetime:
    """Decision timestamps in permisos are written as naive UTC by FastAPI."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value
