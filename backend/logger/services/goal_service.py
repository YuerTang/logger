"""Goals are judged by deliverables, not hours.

A goal ("Blackswan → CVPR 2027") has deliverables, each with a due date.
Status comes from what is done versus what is due:
  - behind:   at least one deliverable is past its due date and not done
  - due_soon: the next open deliverable is due within DUE_SOON_DAYS
  - on_track: otherwise
  - done:     every deliverable is done

Time logged in the goal's categories (today and this week) is returned as
context only.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from logger.models import Category, DailyRecord, Deliverable, Goal, Observation, Setting

DEFAULT_TIMEZONE = "America/Los_Angeles"
DUE_SOON_DAYS = 3


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z一-鿿]", "", (s or "").lower())


async def user_today(db: AsyncSession) -> date:
    row = (await db.execute(select(Setting).where(Setting.key == "timezone"))).scalar_one_or_none()
    tz = (row.value if row else None) or DEFAULT_TIMEZONE
    return datetime.now(ZoneInfo(tz)).date()


async def _logged_minutes(names: list[str], lo: date, hi: date, db: AsyncSession) -> int:
    wanted = {_norm(n) for n in names}
    if not wanted:
        return 0
    cats = (await db.execute(select(Category))).scalars().all()
    ids = [c.id for c in cats if _norm(c.name) in wanted or _norm(c.display_name or "") in wanted]
    if not ids:
        return 0
    total = (await db.execute(
        select(func.sum(Observation.minutes))
        .join(DailyRecord, Observation.daily_record_id == DailyRecord.id)
        .where(Observation.category_id.in_(ids),
               DailyRecord.date >= lo.isoformat(), DailyRecord.date <= hi.isoformat())
    )).scalar()
    return int(total or 0)


def _deliv(d: Deliverable, today: date) -> dict:
    days = (date.fromisoformat(d.due_date) - today).days if d.due_date else None
    return {
        "id": d.id,
        "goal_id": d.goal_id,
        "title": d.title,
        "due_date": d.due_date,
        "done": bool(d.done),
        "done_at": d.done_at,
        "note": d.note,
        "position": d.position,
        "days_until_due": days,
        "overdue": bool(not d.done and days is not None and days < 0),
    }


async def view(goal: Goal, today: date, db: AsyncSession) -> dict:
    items = [_deliv(d, today) for d in goal.deliverables]
    open_ = sorted(
        (i for i in items if not i["done"]),
        key=lambda i: (i["due_date"] is None, i["due_date"] or "", i["position"]),
    )
    done = sum(1 for i in items if i["done"])
    overdue = [i for i in open_ if i["overdue"]]

    if items and not open_:
        status = "done"
    elif overdue:
        status = "behind"
    elif open_ and open_[0]["days_until_due"] is not None and open_[0]["days_until_due"] <= DUE_SOON_DAYS:
        status = "due_soon"
    else:
        status = "on_track"

    names = json.loads(goal.categories or "[]")
    week_start = today - timedelta(days=today.weekday())
    return {
        "id": goal.id,
        "title": goal.title,
        "deadline": goal.deadline,
        "days_left": (date.fromisoformat(goal.deadline) - today).days if goal.deadline else None,
        "categories": names,
        "note": goal.note,
        "position": goal.position,
        "archived": bool(goal.archived),
        "status": status,
        "done_count": done,
        "total_count": len(items),
        "overdue_count": len(overdue),
        "next_up": open_[:3],
        "deliverables": items,
        "time": {
            "today_hours": round(await _logged_minutes(names, today, today, db) / 60, 1),
            "week_hours": round(await _logged_minutes(names, week_start, today, db) / 60, 1),
        },
    }


async def _load(goal_id: int, db: AsyncSession) -> Goal:
    g = (await db.execute(
        select(Goal).options(selectinload(Goal.deliverables)).where(Goal.id == goal_id)
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if not g:
        raise ValueError("Goal not found")
    return g


async def get_view(goal_id: int, db: AsyncSession) -> dict:
    return await view(await _load(goal_id, db), await user_today(db), db)


async def list_goals(db: AsyncSession, include_archived: bool = False) -> list[dict]:
    stmt = (select(Goal).options(selectinload(Goal.deliverables))
            .order_by(Goal.position, Goal.id).execution_options(populate_existing=True))
    if not include_archived:
        stmt = stmt.where(Goal.archived == False)  # noqa: E712
    today = await user_today(db)
    return [await view(g, today, db) for g in (await db.execute(stmt)).scalars().all()]


def _check_date(v: str | None) -> str | None:
    if v:
        date.fromisoformat(v)
    return v or None


async def create_goal(data: dict, db: AsyncSession) -> Goal:
    if not (data.get("title") or "").strip():
        raise ValueError("title is required")
    g = Goal(
        title=data["title"].strip(),
        deadline=_check_date(data.get("deadline")),
        categories=json.dumps(data.get("categories") or []),
        note=data.get("note"),
        position=data.get("position", 0),
    )
    db.add(g)
    await db.flush()
    for i, d in enumerate(data.get("deliverables") or []):
        if not (d.get("title") or "").strip():
            raise ValueError("every deliverable needs a title")
        db.add(Deliverable(
            goal_id=g.id, title=d["title"].strip(), due_date=_check_date(d.get("due_date")),
            done=bool(d.get("done")), note=d.get("note"), position=d.get("position", i),
        ))
    await db.flush()
    return g


async def update_goal(goal_id: int, data: dict, db: AsyncSession) -> None:
    g = await _load(goal_id, db)
    if data.get("title"):
        g.title = data["title"].strip()
    if "deadline" in data:
        g.deadline = _check_date(data["deadline"])
    if "categories" in data:
        g.categories = json.dumps(data["categories"] or [])
    for k in ("note", "position", "archived"):
        if k in data:
            setattr(g, k, data[k])
    await db.flush()


async def delete_goal(goal_id: int, db: AsyncSession) -> None:
    await db.delete(await _load(goal_id, db))
    await db.flush()


async def add_deliverable(goal_id: int, data: dict, db: AsyncSession) -> Deliverable:
    g = await _load(goal_id, db)
    if not (data.get("title") or "").strip():
        raise ValueError("title is required")
    d = Deliverable(
        goal_id=g.id, title=data["title"].strip(), due_date=_check_date(data.get("due_date")),
        note=data.get("note"),
        position=data.get("position", max((x.position or 0 for x in g.deliverables), default=-1) + 1),
    )
    db.add(d)
    await db.flush()
    return d


async def update_deliverable(deliv_id: int, data: dict, db: AsyncSession) -> Deliverable:
    d = await db.get(Deliverable, deliv_id)
    if not d:
        raise ValueError("Deliverable not found")
    if data.get("title"):
        d.title = data["title"].strip()
    if "due_date" in data:
        d.due_date = _check_date(data["due_date"])
    if "note" in data:
        d.note = data["note"]
    if "position" in data:
        d.position = data["position"]
    if "done" in data:
        d.done = bool(data["done"])
        d.done_at = datetime.now(timezone.utc).isoformat(timespec="seconds") if d.done else None
    await db.flush()
    return d


async def delete_deliverable(deliv_id: int, db: AsyncSession) -> int:
    d = await db.get(Deliverable, deliv_id)
    if not d:
        raise ValueError("Deliverable not found")
    gid = d.goal_id
    await db.delete(d)
    await db.flush()
    return gid
