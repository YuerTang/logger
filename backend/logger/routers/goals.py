from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.services import goal_service as gs

router = APIRouter(prefix="/goals", tags=["goals"])


class DeliverableIn(BaseModel):
    title: str | None = None
    due_date: str | None = None
    done: bool | None = None
    note: str | None = None
    position: int | None = None


class GoalIn(BaseModel):
    title: str | None = None
    deadline: str | None = None
    categories: list[str] | None = None
    note: str | None = None
    position: int | None = None
    archived: bool | None = None
    deliverables: list[DeliverableIn] | None = None


def _bad(e: Exception):
    return HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_goals(include_archived: bool = False, db: AsyncSession = Depends(get_db)):
    return await gs.list_goals(db, include_archived)


@router.post("")
async def create_goal(body: GoalIn, db: AsyncSession = Depends(get_db)):
    try:
        g = await gs.create_goal(body.model_dump(exclude_unset=True), db)
        await db.commit()
    except ValueError as e:
        raise _bad(e)
    return await gs.get_view(g.id, db)


@router.post("/import")
async def import_goals(body: list[GoalIn], db: AsyncSession = Depends(get_db)):
    """Create several goals with their deliverables in one go."""
    try:
        for i, g in enumerate(body):
            d = g.model_dump(exclude_unset=True)
            d.setdefault("position", i)
            await gs.create_goal(d, db)
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise _bad(e)
    return await gs.list_goals(db)


@router.put("/{goal_id}")
async def update_goal(goal_id: int, body: GoalIn, db: AsyncSession = Depends(get_db)):
    try:
        await gs.update_goal(goal_id, body.model_dump(exclude_unset=True, exclude={"deliverables"}), db)
        await db.commit()
    except ValueError as e:
        raise _bad(e)
    return await gs.get_view(goal_id, db)


@router.delete("/{goal_id}")
async def delete_goal(goal_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await gs.delete_goal(goal_id, db)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.post("/{goal_id}/deliverables")
async def add_deliverable(goal_id: int, body: DeliverableIn, db: AsyncSession = Depends(get_db)):
    try:
        await gs.add_deliverable(goal_id, body.model_dump(exclude_unset=True), db)
        await db.commit()
    except ValueError as e:
        raise _bad(e)
    return await gs.get_view(goal_id, db)


@router.put("/deliverables/{deliv_id}")
async def update_deliverable(deliv_id: int, body: DeliverableIn, db: AsyncSession = Depends(get_db)):
    try:
        d = await gs.update_deliverable(deliv_id, body.model_dump(exclude_unset=True), db)
        await db.commit()
    except ValueError as e:
        raise _bad(e)
    return await gs.get_view(d.goal_id, db)


@router.delete("/deliverables/{deliv_id}")
async def delete_deliverable(deliv_id: int, db: AsyncSession = Depends(get_db)):
    try:
        gid = await gs.delete_deliverable(deliv_id, db)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return await gs.get_view(gid, db)
