"""Two-way sync between a Notion task database and the Planner.

What syncs
----------
Notion -> log(ger): every task whose date falls in a window around today
becomes a PlanItem (title, date/time, done state). Edits made in Notion flow
in on the next sync.

log(ger) -> Notion: checking a plan item done (or un-done) here flips the
task's checkbox in Notion. Optionally, plan items created here are created
as tasks in Notion too ("push new items").

Notion is the source of truth for title and dates. The done state is synced
both ways; if both sides changed since the last sync, "done" wins.

Which category a task lands in
------------------------------
Notion projects are usually coarser than log(ger) categories ("Fall Classes"
vs "EE227"), so a task is matched in this order:
  1. Keyword rules from settings ("ee 227" -> EE227), checked against the
     task title and its project names.
  2. Automatic: a category of the active session whose name appears in the
     task title, then in a project name (ignoring case, spaces, punctuation).
  3. The default category from settings.
Tasks that match nothing (and with no default set) are skipped and reported.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import Category, PlanItem, Setting
from logger.services.api_key_service import _deobfuscate, _obfuscate
from logger.services.session_service import get_active_session

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Setting keys
K_TOKEN = "notion_token"
K_DB = "notion_tasks_db_id"
K_RULES = "notion_category_rules"        # JSON: [{"match": "ee 227", "category": "EE227"}, ...]
K_DEFAULT_CAT = "notion_default_category"  # category name in the active session
K_PUSH_NEW = "notion_push_new"           # "true" | "false"
K_LAST_SYNC = "notion_last_sync"
K_LAST_RESULT = "notion_last_result"     # JSON summary of the last run
K_PROPS = "notion_property_names"        # JSON override of PROP_DEFAULTS

PROP_DEFAULTS = {"title": "Name", "date": "When", "done": "Complete", "project": "Projects"}

WINDOW_PAST_DAYS = 14
WINDOW_FUTURE_DAYS = 14  # Notion holds short-term tasks; long-term deadlines live in calendars and Goals

DEFAULT_TIMEZONE = "America/Los_Angeles"

# Tests swap this for an httpx.MockTransport.
_transport: httpx.AsyncBaseTransport | None = None


# ── settings helpers ──────────────────────────────────────────────────────

async def _get(db: AsyncSession, key: str) -> str | None:
    row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    return row.value if row else None


async def _set(db: AsyncSession, key: str, value: str | None) -> None:
    row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    if value is None:
        if row:
            await db.delete(row)
        return
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


async def save_token(token: str, db: AsyncSession) -> None:
    await _set(db, K_TOKEN, _obfuscate(token.strip()) if token.strip() else None)
    await db.commit()


async def get_token(db: AsyncSession) -> str | None:
    v = await _get(db, K_TOKEN)
    if not v:
        return None
    try:
        return _deobfuscate(v)
    except Exception:
        return None


def parse_database_id(value: str) -> str:
    """Accept a raw id (with or without dashes) or any Notion URL containing one."""
    m = re.search(
        r"(?<![0-9a-f])([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{32})(?![0-9a-f])",
        value.lower(),
    )
    if not m:
        raise ValueError("Couldn't find a Notion database ID in that text")
    h = m.group(1).replace("-", "")
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


@dataclass
class Config:
    token: str | None
    database_id: str | None
    rules: list[dict]
    default_category: str | None
    push_new: bool
    props: dict
    tz: str

    @property
    def ready(self) -> bool:
        return bool(self.token and self.database_id)


async def load_config(db: AsyncSession) -> Config:
    rules_raw = await _get(db, K_RULES)
    props_raw = await _get(db, K_PROPS)
    try:
        rules = json.loads(rules_raw) if rules_raw else []
    except json.JSONDecodeError:
        rules = []
    try:
        props = {**PROP_DEFAULTS, **(json.loads(props_raw) if props_raw else {})}
    except json.JSONDecodeError:
        props = dict(PROP_DEFAULTS)
    return Config(
        token=await get_token(db),
        database_id=await _get(db, K_DB),
        rules=[r for r in rules if r.get("match") and r.get("category")],
        default_category=(await _get(db, K_DEFAULT_CAT)) or None,
        push_new=(await _get(db, K_PUSH_NEW)) == "true",
        props=props,
        tz=(await _get(db, "timezone")) or DEFAULT_TIMEZONE,
    )


# ── Notion client ─────────────────────────────────────────────────────────

class NotionError(Exception):
    pass


class Notion:
    def __init__(self, token: str):
        self._client = httpx.AsyncClient(
            base_url=NOTION_API,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            timeout=30,
            transport=_transport,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self._client.aclose()

    async def _req(self, method: str, path: str, **kw) -> dict:
        r = await self._client.request(method, path, **kw)
        if r.status_code >= 400:
            try:
                msg = r.json().get("message", r.text)
            except Exception:
                msg = r.text
            if r.status_code == 401:
                msg = "Notion rejected the token. Check it in Settings."
            elif r.status_code == 404:
                msg = ("Notion couldn't find that database. Open it in Notion, "
                       "click ••• → Connections, and add your integration.")
            raise NotionError(msg)
        return r.json()

    async def query(self, database_id: str, body: dict) -> list[dict]:
        out, cursor = [], None
        while True:
            payload = dict(body)
            if cursor:
                payload["start_cursor"] = cursor
            data = await self._req("POST", f"/databases/{database_id}/query", json=payload)
            out.extend(data.get("results", []))
            if not data.get("has_more"):
                return out
            cursor = data.get("next_cursor")

    async def page(self, page_id: str) -> dict:
        return await self._req("GET", f"/pages/{page_id}")

    async def update_page(self, page_id: str, properties: dict) -> dict:
        return await self._req("PATCH", f"/pages/{page_id}", json={"properties": properties})

    async def create_page(self, database_id: str, properties: dict) -> dict:
        return await self._req(
            "POST", "/pages", json={"parent": {"database_id": database_id}, "properties": properties}
        )

    async def database(self, database_id: str) -> dict:
        return await self._req("GET", f"/databases/{database_id}")


# ── parsing ───────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z一-鿿]", "", (s or "").lower())


def _plain(rich: list[dict] | None) -> str:
    return "".join(t.get("plain_text", "") for t in (rich or [])).strip()


def page_title(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return _plain(prop.get("title"))
    return ""


def _split_when(value: str | None, tz: ZoneInfo) -> tuple[str | None, str | None]:
    """Notion date string -> (YYYY-MM-DD, HH:MM or None) in the user's timezone."""
    if not value:
        return None, None
    if len(value) == 10:
        return value, None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(tz)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")


@dataclass
class Task:
    page_id: str
    title: str
    start_date: str
    end_date: str
    start_time: str | None
    end_time: str | None
    done: bool
    project_ids: list[str]
    last_edited: str
    url: str


def parse_task(page: dict, props: dict, tz: ZoneInfo) -> Task | None:
    p = page.get("properties", {})
    when = (p.get(props["date"]) or {}).get("date") or {}
    sd, st = _split_when(when.get("start"), tz)
    if not sd:
        return None
    ed, et = _split_when(when.get("end"), tz)
    title_prop = p.get(props["title"]) or {}
    title = _plain(title_prop.get("title")) or page_title(page) or "Untitled"
    return Task(
        page_id=page["id"],
        title=title,
        start_date=sd,
        end_date=ed or sd,
        start_time=st,
        end_time=et if (ed or sd) == sd else None,
        done=bool((p.get(props["done"]) or {}).get("checkbox")),
        project_ids=[r["id"] for r in (p.get(props["project"]) or {}).get("relation", [])],
        last_edited=page.get("last_edited_time", ""),
        url=page.get("url", ""),
    )


# ── category matching ─────────────────────────────────────────────────────

@dataclass
class Matcher:
    categories: list[Category]
    rules: list[dict]
    default_name: str | None
    by_name: dict[str, Category] = field(default_factory=dict)

    def __post_init__(self):
        for c in self.categories:
            for n in (c.name, c.display_name):
                if n:
                    self.by_name.setdefault(_norm(n), c)

    def find(self, name: str | None) -> Category | None:
        return self.by_name.get(_norm(name or "")) if name else None

    def match(self, title: str, projects: list[str]) -> Category | None:
        t = _norm(title)
        hay = [t] + [_norm(p) for p in projects]
        for r in self.rules:
            key = _norm(r["match"])
            if key and any(key in h for h in hay):
                cat = self.find(r["category"])
                if cat:
                    return cat
        # longest names first so "CS230 Project" beats "CS230"
        cands = sorted(self.by_name.items(), key=lambda kv: -len(kv[0]))
        for h in hay:
            for key, cat in cands:
                if len(key) >= 3 and key in h:
                    return cat
        return self.find(self.default_name)


# ── sync ──────────────────────────────────────────────────────────────────

@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    pushed_done: int = 0
    pushed_new: int = 0
    unmatched: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    synced_at: str = ""

    def as_dict(self) -> dict:
        return self.__dict__.copy()


async def sync(db: AsyncSession, today: date | None = None) -> SyncResult:
    cfg = await load_config(db)
    if not cfg.ready:
        raise NotionError("Add your Notion token and task database in Settings first.")
    session = await get_active_session(db)
    if not session:
        raise NotionError("No active session in log(ger).")

    tz = ZoneInfo(cfg.tz)
    today = today or datetime.now(tz).date()
    lo = (today - timedelta(days=WINDOW_PAST_DAYS)).isoformat()
    hi = (today + timedelta(days=WINDOW_FUTURE_DAYS)).isoformat()

    cats = (await db.execute(select(Category).where(Category.session_id == session.id))).scalars().all()
    matcher = Matcher(list(cats), cfg.rules, cfg.default_category)
    res = SyncResult()

    async with Notion(cfg.token) as notion:
        pages = await notion.query(cfg.database_id, {
            "filter": {"and": [
                {"property": cfg.props["date"], "date": {"on_or_after": lo}},
                {"property": cfg.props["date"], "date": {"on_or_before": hi}},
            ]},
            "page_size": 100,
        })

        project_names: dict[str, str] = {}

        async def names_for(ids: list[str]) -> list[str]:
            out = []
            for pid in ids:
                if pid not in project_names:
                    try:
                        project_names[pid] = page_title(await notion.page(pid))
                    except NotionError:
                        project_names[pid] = ""
                out.append(project_names[pid])
            return out

        existing = {
            it.notion_page_id: it
            for it in (await db.execute(
                select(PlanItem).where(PlanItem.notion_page_id.is_not(None))
            )).scalars().all()
        }

        for page in pages:
            if page.get("archived") or page.get("in_trash"):
                continue
            task = parse_task(page, cfg.props, tz)
            if not task:
                continue
            item = existing.get(task.page_id)
            if item is None:
                cat = matcher.match(task.title, await names_for(task.project_ids))
                if not cat:
                    res.unmatched.append(task.title)
                    continue
                status = "done" if task.done else "planned"
                db.add(PlanItem(
                    title=task.title, category_id=cat.id,
                    start_date=task.start_date, end_date=task.end_date,
                    start_time=task.start_time, end_time=task.end_time,
                    status=status, notes=task.url or None,
                    notion_page_id=task.page_id, notion_last_edited=task.last_edited,
                    notion_synced_status=status,
                ))
                res.created += 1
                continue

            notion_changed = task.last_edited != item.notion_last_edited
            local_changed = item.status != item.notion_synced_status
            notion_status = "done" if task.done else "planned"

            if notion_changed:
                item.title = task.title
                item.start_date, item.end_date = task.start_date, task.end_date
                item.start_time, item.end_time = task.start_time, task.end_time
                item.notion_last_edited = task.last_edited
                if not local_changed or notion_status == "done":
                    item.status = notion_status
                res.updated += 1

            if item.status != notion_status:
                try:
                    updated = await notion.update_page(
                        task.page_id, {cfg.props["done"]: {"checkbox": item.status == "done"}}
                    )
                    item.notion_last_edited = updated.get("last_edited_time", item.notion_last_edited)
                    res.pushed_done += 1
                except NotionError as e:
                    res.errors.append(f"{task.title}: {e}")
                    continue
            item.notion_synced_status = item.status

        # Items whose Notion page left the window (or was deleted) but were
        # toggled here: push the checkbox directly.
        seen = {p["id"] for p in pages}
        for pid, item in existing.items():
            if pid in seen or item.status == item.notion_synced_status:
                continue
            try:
                updated = await notion.update_page(pid, {cfg.props["done"]: {"checkbox": item.status == "done"}})
                item.notion_last_edited = updated.get("last_edited_time", item.notion_last_edited)
                item.notion_synced_status = item.status
                res.pushed_done += 1
            except NotionError as e:
                res.errors.append(f"{item.title}: {e}")

        if cfg.push_new:
            await _push_new(db, notion, cfg, tz, session.id, lo, hi, res)

    res.synced_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    await _set(db, K_LAST_SYNC, res.synced_at)
    await _set(db, K_LAST_RESULT, json.dumps(res.as_dict()))
    await db.commit()
    return res


async def _push_new(db, notion: Notion, cfg: Config, tz: ZoneInfo, session_id: int, lo: str, hi: str, res: SyncResult) -> None:
    """Create Notion tasks for plan items made in log(ger) (active session, in window)."""
    rows = (await db.execute(
        select(PlanItem, Category)
        .join(Category, PlanItem.category_id == Category.id)
        .where(
            PlanItem.notion_page_id.is_(None),
            Category.session_id == session_id,
            PlanItem.end_date >= lo,
            PlanItem.start_date <= hi,
        )
    )).all()
    for item, _cat in rows:
        if item.start_time:
            local = datetime.fromisoformat(f"{item.start_date}T{item.start_time}").replace(tzinfo=tz)
            when = {"start": local.isoformat()}
        else:
            when = {"start": item.start_date}
            if item.end_date != item.start_date:
                when["end"] = item.end_date
        props = {
            cfg.props["title"]: {"title": [{"text": {"content": item.title}}]},
            cfg.props["date"]: {"date": when},
            cfg.props["done"]: {"checkbox": item.status == "done"},
        }
        try:
            page = await notion.create_page(cfg.database_id, props)
        except NotionError as e:
            res.errors.append(f"{item.title}: {e}")
            continue
        item.notion_page_id = page["id"]
        item.notion_last_edited = page.get("last_edited_time")
        item.notion_synced_status = item.status
        res.pushed_new += 1


async def status(db: AsyncSession) -> dict:
    cfg = await load_config(db)
    last = await _get(db, K_LAST_RESULT)
    return {
        "has_token": bool(cfg.token),
        "database_id": cfg.database_id,
        "rules": cfg.rules,
        "default_category": cfg.default_category,
        "push_new": cfg.push_new,
        "last_sync": await _get(db, K_LAST_SYNC),
        "last_result": json.loads(last) if last else None,
    }


async def save_config(db: AsyncSession, *, database: str | None = None, rules: list[dict] | None = None,
                      default_category: str | None = None, push_new: bool | None = None) -> None:
    if database is not None:
        await _set(db, K_DB, parse_database_id(database) if database.strip() else None)
    if rules is not None:
        clean = [{"match": r["match"].strip(), "category": r["category"].strip()}
                 for r in rules if r.get("match", "").strip() and r.get("category", "").strip()]
        await _set(db, K_RULES, json.dumps(clean))
    if default_category is not None:
        await _set(db, K_DEFAULT_CAT, default_category.strip() or None)
    if push_new is not None:
        await _set(db, K_PUSH_NEW, "true" if push_new else "false")
    await db.commit()


async def test_connection(db: AsyncSession) -> dict:
    cfg = await load_config(db)
    if not cfg.ready:
        raise NotionError("Add your Notion token and task database first.")
    async with Notion(cfg.token) as notion:
        d = await notion.database(cfg.database_id)
    have = d.get("properties", {})
    missing = [v for v in cfg.props.values() if v not in have]
    return {"title": _plain(d.get("title")), "missing_properties": missing}
