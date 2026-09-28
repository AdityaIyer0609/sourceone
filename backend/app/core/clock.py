from datetime import UTC, date, datetime, time, timedelta, timezone

from app.core.config import get_settings


def utcnow() -> datetime:
    return datetime.now(UTC)


def business_tz() -> timezone:
    return timezone(timedelta(minutes=get_settings().business_utc_offset_minutes))


def business_today(now: datetime | None = None) -> date:
    return (now or utcnow()).astimezone(business_tz()).date()


def start_of_business_day(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=business_tz()).astimezone(UTC)
