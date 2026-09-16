from datetime import date as date_type, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.models import (
    Session, DailyRecord, Observation, TimerEntry, ManualEntry, Category,
    BreakDay,
)
from logger.services.session_service import resolve_session_for_date
from logger.schemas import (
    DailyActivityResponse, TimerEntryResponse, ManualEntryResponse,
    ObservationResponse, StreakResponse,
)

router = APIRouter(prefix="/daily", tags=["daily"])


@router.get("/{date}", response_model=DailyActivityResponse)
async def get_daily_activity(date: str, db: AsyncSession = Depends(get_db)):
    session = await resolve_session_for_date(date, db)
    if not session:
        raise HTTPException(status_code=400, detail="No active session")

    # Daily record + observations
    dr_result = await db.execute(
        select(DailyRecord).where(
            DailyRecord.session_id == session.id,
            DailyRecord.date == date,
        )
    )
    daily_record = dr_result.scalar_one_or_none()

    observations = []
    total_minutes = 0
    if daily_record:
        total_minutes = daily_record.total_minutes
        # Only include observations whose source is 'import' — timer/manual
        # observations are already represented by their underlying entry rows
        # (the T and M rows in TodayLog), so including them all would render
        # the same minutes twice.
        obs_result = await db.execute(
            select(Observation).where(
                Observation.daily_record_id == daily_record.id,
                Observation.source == "import",
            )
        )
        for obs in obs_result.scalars().all():
            cat = await db.get(Category, obs.category_id)
            observations.append(ObservationResponse(
                id=obs.id,
                category_id=obs.category_id,
                category_name=cat.display_name or cat.name if cat else None,
                minutes=obs.minutes,
                source=obs.source,
            ))

    # Completed timer entries for this date
    timer_result = await db.execute(
        select(TimerEntry).where(
            TimerEntry.session_id == session.id,
            TimerEntry.date == date,
            TimerEntry.is_active == False,
        ).order_by(TimerEntry.end_time.desc())
    )
    timer_entries = []
    for t in timer_result.scalars().all():
        cat = await db.get(Category, t.category_id)
        timer_entries.append(TimerEntryResponse(
            id=t.id,
            session_id=t.session_id,
            category_id=t.category_id,
            category_name=cat.display_name or cat.name if cat else None,
            date=t.date,
            start_time=t.start_time,
            end_time=t.end_time,
            pause_start=t.pause_start,
            total_paused_seconds=t.total_paused_seconds or 0,
            duration_minutes=t.duration_minutes,
            is_active=t.is_active,
            is_paused=t.is_paused,
            description=t.description,
            location=t.location,
        ))

    # Manual entries for this date
    manual_result = await db.execute(
        select(ManualEntry).where(
            ManualEntry.session_id == session.id,
            ManualEntry.date == date,
        ).order_by(ManualEntry.created_at.desc())
    )
    manual_entries = []
    for m in manual_result.scalars().all():
        cat = await db.get(Category, m.category_id)
        manual_entries.append(ManualEntryResponse(
            id=m.id,
            session_id=m.session_id,
            category_id=m.category_id,
            category_name=cat.display_name or cat.name if cat else None,
            date=m.date,
            duration_minutes=m.duration_minutes,
            description=m.description,
            location=m.location,
            start_time=m.start_time,
            created_at=m.created_at,
        ))

    # Break marker (global, not session-scoped).
    break_result = await db.execute(
        select(BreakDay).where(BreakDay.date == date)
    )
    break_day = break_result.scalar_one_or_none()

    return DailyActivityResponse(
        date=date,
        session_id=session.id,
        session_label=session.label,
        total_minutes=total_minutes,
        timer_entries=timer_entries,
        manual_entries=manual_entries,
        observations=observations,
        is_break=break_day is not None,
        break_label=break_day.label if break_day else None,
    )


@router.get("/streak/current", response_model=StreakResponse)
async def get_streak(db: AsyncSession = Depends(get_db)):
    session = await _get_active_session(db)
    if not session:
        return StreakResponse(current=0, longest=0)

    # Get all dates with logged time, ordered
    result = await db.execute(
        select(DailyRecord.date)
        .where(
            DailyRecord.session_id == session.id,
            DailyRecord.total_minutes > 0,
        )
        .order_by(DailyRecord.date.desc())
    )
    worked = {date_type.fromisoformat(row[0]) for row in result.all()}

    # Break days bridge the streak: they neither count toward it nor break it.
    # A run of work days separated only by breaks stays a single streak.
    break_result = await db.execute(select(BreakDay.date))
    breaks = {date_type.fromisoformat(row[0]) for row in break_result.all()}

    if not worked:
        return StreakResponse(current=0, longest=0)

    one_day = timedelta(days=1)

    def walk_back(start: date_type) -> int:
        """Walk backwards counting work days, stepping over break days, until a
        day that is neither worked nor a break (a real gap) is hit."""
        count = 0
        d = start
        while True:
            if d in worked:
                count += 1
                d -= one_day
            elif d in breaks:
                d -= one_day  # bridge — no increment
            else:
                break
        return count

    today = date_type.today()
    current = walk_back(today)
    # Grace: today may not be logged yet. If today is a real gap, count the
    # streak ending yesterday instead (matches prior behavior, break-aware).
    if current == 0 and today not in worked and today not in breaks:
        current = walk_back(today - one_day)

    # Longest streak across all history, bridging breaks. Walk calendar-contiguous
    # runs over (worked ∪ breaks) and count only the work days within each run.
    relevant = sorted(worked | breaks)
    longest = 0
    run_worked = 0
    prev: date_type | None = None
    for d in relevant:
        if prev is not None and d - prev == one_day:
            run_worked += 1 if d in worked else 0
        else:
            run_worked = 1 if d in worked else 0
        longest = max(longest, run_worked)
        prev = d

    return StreakResponse(current=current, longest=longest)


async def _get_active_session(db: AsyncSession) -> Session | None:
    result = await db.execute(
        select(Session).where(Session.is_active == True)
    )
    return result.scalar_one_or_none()

