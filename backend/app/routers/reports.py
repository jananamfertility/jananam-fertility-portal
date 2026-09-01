"""
Admin panel — booking reports.

Volume here is small (well under a thousand rows a year), so this simply
pulls the rows in range and aggregates in Python rather than pushing
group-by logic into Postgres — easier to read and plenty fast at this
scale.
"""
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

from ..auth import StaffUser, get_current_staff
from ..database import get_supabase
from ..schemas import ReportSummary

router = APIRouter(prefix="/api/reports", tags=["reports"])

_WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _default_month_range() -> tuple[datetime, datetime]:
    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


@router.get("/summary", response_model=ReportSummary)
def summary(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    _staff: StaffUser = Depends(get_current_staff),
):
    if start is None or end is None:
        start, end = _default_month_range()

    supabase = get_supabase()

    providers = supabase.table("providers").select("id, name").execute().data
    provider_names = {p["id"]: p["name"] for p in providers}

    rows = (
        supabase.table("appointments")
        .select("appointment_type, status, starts_at, provider_id")
        .gte("starts_at", start.isoformat())
        .lt("starts_at", end.isoformat())
        .execute()
        .data
    )

    total = len(rows)
    by_type: Counter = Counter()
    by_status: Counter = Counter()
    by_weekday: Counter = Counter()
    by_provider: Counter = Counter()

    for row in rows:
        by_type[row["appointment_type"]] += 1
        by_status[row["status"]] += 1
        if row["status"] != "cancelled":
            weekday = _WEEKDAY_NAMES[_parse(row["starts_at"]).weekday()]
            by_weekday[weekday] += 1
            provider_label = provider_names.get(row["provider_id"], "Unassigned")
            by_provider[provider_label] += 1

    cancelled = by_status.get("cancelled", 0)
    no_show = by_status.get("no_show", 0)
    kept = total - cancelled

    return ReportSummary(
        range_start=start,
        range_end=end,
        total=total,
        kept=kept,
        by_type=dict(by_type),
        by_status=dict(by_status),
        by_weekday=dict(by_weekday),
        by_provider=dict(by_provider),
        no_show_rate=round(no_show / kept, 4) if kept else 0.0,
        cancellation_rate=round(cancelled / total, 4) if total else 0.0,
    )
