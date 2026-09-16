"""Mapping calendar days onto the session that owns them."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import Session, DailyRecord


async def get_active_session(db: AsyncSession) -> Session | None:
    result = await db.execute(select(Session).where(Session.is_active == True))  # noqa: E712
    return result.scalar_one_or_none()


async def resolve_session_for_date(date: str, db: AsyncSession) -> Session | None:
    """The session a given calendar day belongs to.

    The recorder lets you page back to any past day, and once a session is
    archived those days live in it, not in the active one — so scoping by the
    active session alone renders every past day empty. Prefer the session that
    actually holds a daily record for the date; a handful of legacy sessions
    have overlapping start/end ranges, so only fall back to a range match, and
    then to the active session for a day nothing has been logged on yet.
    """
    owning = (await db.execute(
        select(Session)
        .join(DailyRecord, DailyRecord.session_id == Session.id)
        .where(DailyRecord.date == date)
    )).scalars().all()

    if not owning:
        owning = (await db.execute(
            select(Session).where(
                Session.start_date.is_not(None),
                Session.end_date.is_not(None),
                Session.start_date <= date,
                Session.end_date >= date,
            )
        )).scalars().all()

    if not owning:
        return await get_active_session(db)
    if len(owning) == 1:
        return owning[0]

    # Ambiguous (overlapping legacy ranges): the active session wins, else the
    # one that started most recently.
    active = await get_active_session(db)
    if active and any(s.id == active.id for s in owning):
        return active
    return max(owning, key=lambda s: s.start_date or "")
