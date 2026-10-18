"""End-to-end tests for Notion sync and goals against a fake Notion API."""
import json
from datetime import date

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from logger.database import async_session, init_db
from logger.main import app
from logger.models import Category, DailyRecord, Observation, Session
from logger.services import notion_sync_service as ns

pytestmark = pytest.mark.asyncio

DB_ID = "28cb83fa-b7aa-81a2-b401-f33a7122c366"
FALL = "3c4b83fa-b7aa-81ff-a780-e6b73de72b39"
ADMIN = "3c4b83fa-b7aa-81f6-954e-fbc0a0c340ea"


class FakeNotion:
    def __init__(self):
        self.pages = {}
        self.calls = []
        self.edits = 0

    def add(self, pid, title, start, done=False, projects=(), end=None):
        self.edits += 1
        self.pages[pid] = {
            "id": pid, "url": f"https://notion.so/{pid}", "archived": False,
            "last_edited_time": f"2026-10-18T00:00:{self.edits:02d}.000Z",
            "properties": {
                "Name": {"type": "title", "title": [{"plain_text": title}]},
                "When": {"type": "date", "date": {"start": start, "end": end}},
                "Complete": {"type": "checkbox", "checkbox": done},
                "Projects": {"type": "relation", "relation": [{"id": p} for p in projects]},
            },
        }

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls.append((req.method, req.url.path))
        path = req.url.path.removeprefix("/v1")
        if req.method == "POST" and path == f"/databases/{DB_ID}/query":
            return httpx.Response(200, json={"results": list(self.pages.values()), "has_more": False})
        if req.method == "GET" and path == f"/databases/{DB_ID}":
            return httpx.Response(200, json={"title": [{"plain_text": "Tasks"}], "properties": {"Name": {}, "When": {}, "Complete": {}, "Projects": {}}})
        if req.method == "GET" and path.startswith("/pages/"):
            pid = path.split("/")[-1]
            name = {FALL: "Fall Classes", ADMIN: "Life Admin"}.get(pid, "?")
            return httpx.Response(200, json={"id": pid, "properties": {"Name": {"type": "title", "title": [{"plain_text": name}]}}})
        if req.method == "PATCH" and path.startswith("/pages/"):
            pid = path.split("/")[-1]
            body = json.loads(req.content)
            self.pages[pid]["properties"]["Complete"]["checkbox"] = body["properties"]["Complete"]["checkbox"]
            self.edits += 1
            self.pages[pid]["last_edited_time"] = f"2026-10-18T00:01:{self.edits:02d}.000Z"
            return httpx.Response(200, json=self.pages[pid])
        if req.method == "POST" and path == "/pages":
            body = json.loads(req.content)
            pid = f"new-{len(self.pages)}"
            title = body["properties"]["Name"]["title"][0]["text"]["content"]
            self.add(pid, title, body["properties"]["When"]["date"]["start"])
            return httpx.Response(200, json=self.pages[pid])
        return httpx.Response(404, json={"message": "nope"})


@pytest.fixture
async def setup():
    from logger.database import engine
    from logger.models import Base
    from sqlalchemy import text
    async with engine.begin() as conn:
        for v in ("v_daily_totals", "v_family_totals"):
            await conn.execute(text(f"DROP VIEW IF EXISTS {v}"))
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    async with async_session() as db:
        s = Session(year=2026, season="Fall", label="Fall 2026", is_active=True)
        db.add(s)
        await db.flush()
        for n in ["EE227", "CS230", "Blackswan", "ESM", "Singapore", "Logistics"]:
            db.add(Category(session_id=s.id, name=n, display_name=n))
        await db.commit()
    fake = FakeNotion()
    ns._transport = httpx.MockTransport(fake.handler)
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
    await client.put("/api/settings/timezone", json={"value": "Asia/Shanghai"})
    yield client, fake
    await client.aclose()


async def test_notion_sync_roundtrip(setup):
    client, fake = setup
    fake.add("p1", "EE 227 HW 2 due (5pm PT)", "2026-10-20T00:00:00.000Z", projects=[FALL])
    fake.add("p2", "交学费", "2026-10-17")
    fake.add("p3", "Book CS 230 TA meeting", "2026-10-16", projects=[FALL])
    fake.add("p4", "Renew passport", "2026-10-22", projects=[ADMIN])

    assert (await client.put("/api/notion/token", json={"token": "secret_x"})).json()["has_token"]
    r = await client.put("/api/notion/config", json={
        "database": f"https://www.notion.so/Tasks-{DB_ID.replace('-', '')}?v=abc123abc123abc123abc123abc123ab",
        "rules": [{"match": "Life Admin", "category": "Logistics"}],
    })
    assert r.json()["database_id"] == DB_ID
    assert (await client.post("/api/notion/test")).json()["missing_properties"] == []

    res = (await client.post("/api/notion/sync")).json()
    assert res["created"] == 3, res
    assert res["unmatched"] == ["交学费"]

    items = (await client.get("/api/planner/items?start=2026-10-01&end=2026-10-31")).json()
    by = {i["title"]: i for i in items}
    hw = by["EE 227 HW 2 due (5pm PT)"]
    assert hw["category_name"] == "EE227"
    assert (hw["start_date"], hw["start_time"]) == ("2026-10-20", "08:00")  # UTC -> Shanghai
    assert by["Book CS 230 TA meeting"]["category_name"] == "CS230"
    assert by["Renew passport"]["category_name"] == "Logistics"

    # default category picks up the unmatched one
    await client.put("/api/notion/config", json={"default_category": "Logistics"})
    assert (await client.post("/api/notion/sync")).json()["created"] == 1

    # done in log(ger) -> checkbox in Notion
    await client.put(f"/api/planner/items/{hw['id']}", json={"status": "done"})
    res = (await client.post("/api/notion/sync")).json()
    assert res["pushed_done"] == 1 and fake.pages["p1"]["properties"]["Complete"]["checkbox"] is True

    # checked + renamed in Notion -> flows in
    fake.add("p3", "Book CS 230 TA meeting (Calendly)", "2026-10-17", done=True, projects=[FALL])
    res = (await client.post("/api/notion/sync")).json()
    assert res["updated"] == 1 and res["pushed_done"] == 0
    items = (await client.get("/api/planner/items?start=2026-10-01&end=2026-10-31")).json()
    cs = next(i for i in items if i["notion_page_id"] == "p3")
    assert cs["title"].endswith("(Calendly)") and cs["status"] == "done" and cs["start_date"] == "2026-10-17"

    # nothing changed -> nothing written
    res = (await client.post("/api/notion/sync")).json()
    assert (res["created"], res["updated"], res["pushed_done"]) == (0, 0, 0)


async def test_push_new_items(setup):
    client, fake = setup
    await client.put("/api/notion/token", json={"token": "secret_x"})
    await client.put("/api/notion/config", json={"database": DB_ID, "push_new": True})
    async with async_session() as db:
        from sqlalchemy import select
        cat = (await db.execute(select(Category).where(Category.name == "Blackswan"))).scalars().first()
    today = date.today().isoformat()
    await client.post("/api/planner/items", json={"title": "Draft related work", "category_id": cat.id, "start_date": today, "start_time": "09:00"})
    res = (await client.post("/api/notion/sync")).json()
    assert res["pushed_new"] >= 1
    assert any(p["properties"]["Name"]["title"][0]["plain_text"] == "Draft related work" for p in fake.pages.values())


async def test_goals_by_deliverables(setup):
    client, _ = setup
    from datetime import timedelta
    async with async_session() as db:
        from sqlalchemy import select
        cat = (await db.execute(select(Category).where(Category.name == "Blackswan"))).scalars().first()
        today = date.today()
        dr = DailyRecord(session_id=cat.session_id, date=today.isoformat(), total_minutes=90)
        db.add(dr)
        await db.flush()
        db.add(Observation(daily_record_id=dr.id, category_id=cat.id, minutes=90))
        await db.commit()
    d = lambda n: (today + timedelta(days=n)).isoformat()
    r = await client.post("/api/goals/import", json=[{
        "title": "Blackswan → CVPR", "deadline": d(28), "categories": ["blackswan"],
        "deliverables": [
            {"title": "Questionnaire pilot", "due_date": d(-1)},
            {"title": "Annotation done", "due_date": d(2)},
            {"title": "Submit", "due_date": d(28)},
        ],
    }])
    assert r.status_code == 200, r.text
    g = r.json()[0]
    assert g["status"] == "behind" and g["overdue_count"] == 1
    assert [x["title"] for x in g["next_up"]] == ["Questionnaire pilot", "Annotation done", "Submit"]
    assert g["time"]["today_hours"] == 1.5 and g["days_left"] == 28

    pilot = g["next_up"][0]["id"]
    g = (await client.put(f"/api/goals/deliverables/{pilot}", json={"done": True})).json()
    assert g["status"] == "due_soon" and g["done_count"] == 1

    g = (await client.post(f"/api/goals/{g['id']}/deliverables", json={"title": "Rebuttal prep"})).json()
    assert g["total_count"] == 4 and g["next_up"][-1]["title"] == "Rebuttal prep"  # undated sorts last

    for x in g["deliverables"]:
        if not x["done"]:
            g = (await client.put(f"/api/goals/deliverables/{x['id']}", json={"done": True})).json()
    assert g["status"] == "done"
    assert (await client.delete(f"/api/goals/{g['id']}")).json() == {"ok": True}
    assert (await client.get("/api/goals")).json() == []
