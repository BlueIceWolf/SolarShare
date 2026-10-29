"""Shared calendar boundaries for current and previous billing periods.

Only actual observed meter intervals are summed. Previous periods are never
synthesized from current totals or filled from recorder gaps.
"""

from datetime import date, timedelta

WRITTEN_PERIODS = ("lifetime", "day", "week", "month", "year")
DISPLAY_PERIODS = (
    "lifetime", "day", "week", "last_week", "month", "last_month", "year"
)


def period_key(period, day):
    current = date.fromisoformat(day)
    monday = current - timedelta(days=current.weekday())
    if period == "lifetime":
        return "lifetime"
    if period == "day":
        return f"day:{day}"
    if period == "week":
        return f"week:{monday.isoformat()}"
    if period == "last_week":
        return f"week:{(monday - timedelta(days=7)).isoformat()}"
    if period == "month":
        return f"month:{current:%Y-%m}"
    if period == "last_month":
        first = current.replace(day=1)
        return f"month:{(first - timedelta(days=1)):%Y-%m}"
    if period == "year":
        return f"year:{current:%Y}"
    raise ValueError(f"Unknown accounting period: {period}")


def retained_period_keys(day):
    """Current and previous weeks/months remain available across reloads."""
    return {
        period_key(period, day)
        for period in ("lifetime", "day", "week", "last_week", "month", "last_month", "year")
    }
