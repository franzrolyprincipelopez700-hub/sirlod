from datetime import UTC, datetime
from zoneinfo import ZoneInfo

LIMA = ZoneInfo("America/Lima")


def campus_now() -> datetime:
    return datetime.now(LIMA)


def utc_now() -> datetime:
    return datetime.now(UTC)

