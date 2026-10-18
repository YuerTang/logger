from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.models import Category
from logger.schemas import PlanItemCreate, PlanItemUpdate, PlanItemResponse, PlanItemDetailResponse
from logger.services import planner_service
from logger.routers.timers import _timer_response
from logger.routers.manual_entries import _entry_response

router = APIRouter(prefix="/planner", tags=["planner"])


async def _item_response(item, progress: dict, db: AsyncSession) -> PlanItemResponse:
    cat = await db.get(Category, item.category_id)
    return PlanItemResponse(
        id=item.id,
        title=item.title,
        notes=item.notes,
        category_id=item.category_id,
        category_name=cat.display_name or cat.name if cat else None,
        start_date=item.start_date,
        end_date=item.end_date,
        start_time=item.start_time,
        end_time=item.end_time,
        status=item.status,
        importance=item.importance,
        timer_count=progress["timer_count"],
        manual_count=progress["manual_count"],
        logged_minutes=progress["logged_minutes"],
        created_at=item.created_at,
        notion_page_id=item.notion_page_id,
    )


@router.get("/items", response_model=list[PlanItemResponse])
async def list_plan_items(
    start: str = Query(...),
    end: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    rows = await planner_service.list_items_in_range(start, end, db)
    return [await _item_response(item, progress, db) for item, progress in rows]


@router.post("/items", response_model=PlanItemResponse)
async def create_plan_item(data: PlanItemCreate, db: AsyncSession = Depends(get_db)):
    try:
        item = await planner_service.create_item(
            title=data.title,
            category_id=data.category_id,
            start_date=data.start_date,
            end_date=data.end_date,
            start_time=data.start_time,
            end_time=data.end_time,
            notes=data.notes,
            importance=data.importance,
            db=db,
        )
        await db.commit()
        return await _item_response(item, {"timer_count": 0, "manual_count": 0, "logged_minutes": 0}, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/items/{item_id}", response_model=PlanItemDetailResponse)
async def get_plan_item(item_id: int, db: AsyncSession = Depends(get_db)):
    result = await planner_service.get_item_with_links(item_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Plan item not found")
    item, progress, timers, manuals = result
    base = await _item_response(item, progress, db)
    return PlanItemDetailResponse(
        **base.model_dump(),
        timer_entries=[await _timer_response(t, db) for t in timers],
        manual_entries=[await _entry_response(m, db) for m in manuals],
    )


@router.put("/items/{item_id}", response_model=PlanItemResponse)
async def update_plan_item(item_id: int, data: PlanItemUpdate, db: AsyncSession = Depends(get_db)):
    try:
        item = await planner_service.update_item(
            item_id,
            db,
            title=data.title,
            category_id=data.category_id,
            start_date=data.start_date,
            end_date=data.end_date,
            start_time=data.start_time,
            end_time=data.end_time,
            notes=data.notes,
            status=data.status,
            importance=data.importance,
        )
        await db.commit()
        result = await planner_service.get_item_with_links(item_id, db)
        _, progress, _, _ = result
        return await _item_response(item, progress, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/items/{item_id}")
async def delete_plan_item(item_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await planner_service.delete_item(item_id, db)
        await db.commit()
        return {"detail": "Plan item deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
