from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from logger.database import get_db
from logger.services import notion_sync_service as ns

router = APIRouter(prefix="/notion", tags=["notion"])


class TokenIn(BaseModel):
    token: str


class Rule(BaseModel):
    match: str
    category: str


class ConfigIn(BaseModel):
    database: str | None = None
    rules: list[Rule] | None = None
    default_category: str | None = None
    push_new: bool | None = None


@router.get("/status")
async def get_status(db: AsyncSession = Depends(get_db)):
    return await ns.status(db)


@router.put("/token")
async def put_token(data: TokenIn, db: AsyncSession = Depends(get_db)):
    await ns.save_token(data.token, db)
    return await ns.status(db)


@router.delete("/token")
async def delete_token(db: AsyncSession = Depends(get_db)):
    await ns.save_token("", db)
    return await ns.status(db)


@router.put("/config")
async def put_config(data: ConfigIn, db: AsyncSession = Depends(get_db)):
    try:
        await ns.save_config(
            db,
            database=data.database,
            rules=[r.model_dump() for r in data.rules] if data.rules is not None else None,
            default_category=data.default_category,
            push_new=data.push_new,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await ns.status(db)


@router.post("/test")
async def test(db: AsyncSession = Depends(get_db)):
    try:
        return await ns.test_connection(db)
    except ns.NotionError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sync")
async def run_sync(db: AsyncSession = Depends(get_db)):
    try:
        return (await ns.sync(db)).as_dict()
    except ns.NotionError as e:
        raise HTTPException(status_code=400, detail=str(e))
