import shutil
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text as sa_text

from logger.config import DATABASE_URL, DB_PATH
from logger.models import Base

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


SQLITE_MAGIC = b"SQLite format 3\x00"

V_DAILY_TOTALS = """
CREATE VIEW v_daily_totals AS
SELECT
    dr.date,
    dr.session_id,
    s.label AS session_label,
    c.id AS category_id,
    c.display_name AS category_name,
    cf.name AS family_name,
    cf.color AS family_color,
    dr.week_number,
    COALESCE(o.minutes, 0) AS minutes,
    o.source
FROM daily_records dr
JOIN sessions s ON dr.session_id = s.id
JOIN observations o ON o.daily_record_id = dr.id
JOIN categories c ON o.category_id = c.id
LEFT JOIN category_families cf ON c.family_id = cf.id
"""

V_FAMILY_TOTALS = """
CREATE VIEW v_family_totals AS
SELECT
    cf.id AS family_id,
    cf.name AS family_name,
    cf.display_name,
    cf.color,
    s.id AS session_id,
    s.label AS session_label,
    s.year,
    s.season,
    SUM(o.minutes) AS total_minutes,
    COUNT(DISTINCT dr.date) AS active_days
FROM category_families cf
JOIN categories c ON c.family_id = cf.id
JOIN observations o ON o.category_id = c.id
JOIN daily_records dr ON o.daily_record_id = dr.id
JOIN sessions s ON c.session_id = s.id
GROUP BY cf.id, s.id
"""


async def _migrate_schema(conn) -> None:
    """Idempotent ALTERs for columns SQLAlchemy create_all can't add to existing tables.

    SQLite has no IF NOT EXISTS for ADD COLUMN, so we probe via PRAGMA first.
    """
    async def add_col_if_missing(table: str, col: str, ddl: str) -> None:
        result = await conn.execute(sa_text(f"PRAGMA table_info({table})"))
        existing = {row[1] for row in result.fetchall()}
        if col not in existing:
            await conn.execute(sa_text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))

    await add_col_if_missing("category_families", "group_id", "group_id INTEGER REFERENCES category_groups(id) ON DELETE SET NULL")
    await add_col_if_missing("category_groups", "position", "position INTEGER DEFAULT 0")
    await add_col_if_missing("category_groups", "is_system", "is_system BOOLEAN DEFAULT 0")
    await add_col_if_missing("manual_entries", "start_time", "start_time TEXT")
    await add_col_if_missing("timer_entries", "plan_item_id", "plan_item_id INTEGER REFERENCES plan_items(id) ON DELETE SET NULL")
    await add_col_if_missing("manual_entries", "plan_item_id", "plan_item_id INTEGER REFERENCES plan_items(id) ON DELETE SET NULL")
    await add_col_if_missing("plan_items", "importance", "importance TEXT")
    await add_col_if_missing("plan_items", "notion_page_id", "notion_page_id TEXT")
    await add_col_if_missing("plan_items", "notion_last_edited", "notion_last_edited TEXT")
    await add_col_if_missing("plan_items", "notion_synced_status", "notion_synced_status TEXT")


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_schema(conn)
        # Recreate views to pick up schema changes
        await conn.execute(sa_text("DROP VIEW IF EXISTS v_daily_totals"))
        await conn.execute(sa_text(V_DAILY_TOTALS))
        await conn.execute(sa_text("DROP VIEW IF EXISTS v_family_totals"))
        await conn.execute(sa_text(V_FAMILY_TOTALS))

    # Seed groups, then default families + match rules (all idempotent).
    # The second seed pass is intentional: migrate_family_types_to_groups can
    # fold/delete families (e.g. topomimic, code2action → salk) which cascades
    # their match rules. Re-running the seed afterwards re-creates any rules
    # that the new seed config points at the salk family (or any other surviving
    # family) so detection works on the same boot, not the next one.
    from logger.services.family_service import seed_default_families_and_rules, link_orphans_to_seed_families
    from logger.services.group_service import seed_default_groups, migrate_family_types_to_groups
    from logger.services.timer_service import realign_timer_dates_to_user_tz
    from logger.models import Setting
    from sqlalchemy import select
    async with async_session() as session:
        await seed_default_groups(session)
        await seed_default_families_and_rules(session)
        await migrate_family_types_to_groups(session)
        await seed_default_families_and_rules(session)
        # Retroactively link orphan categories to any newly-seeded families
        # (e.g. Enigmorphic added later → linked to its Research family here).
        await link_orphans_to_seed_families(session)
        # Realign timer dates that were stored in UTC instead of the user's
        # local tz (one-shot fix for entries created before the tz-aware patch).
        await realign_timer_dates_to_user_tz(session)
        # Seed default timezone setting (idempotent — skipped if already set).
        existing_tz = await session.execute(select(Setting).where(Setting.key == "timezone"))
        if not existing_tz.scalar_one_or_none():
            session.add(Setting(key="timezone", value="America/Los_Angeles"))
            await session.commit()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def replace_db_file(new_bytes: bytes) -> dict:
    """Atomically swap the on-disk SQLite file with uploaded bytes.

    Validates magic bytes, smoke-tests the candidate DB by opening it once,
    backs up the current DB to {path}.bak.{timestamp}, swaps files, disposes
    the engine pool so the next connection opens the new inode, and runs
    init_db so any older schema gets the migrations applied.

    The caller (settings router) is responsible for ensuring no other request
    is in flight when this runs — for a single-user local app this is fine.
    """
    if not new_bytes.startswith(SQLITE_MAGIC):
        raise ValueError("Uploaded file is not a SQLite database (bad magic bytes).")

    pending = DB_PATH.with_suffix(DB_PATH.suffix + ".pending")
    pending.write_bytes(new_bytes)

    # Smoke-test: open the candidate file with a one-shot engine and run a trivial query
    probe_url = f"sqlite+aiosqlite:///{pending}"
    probe_engine = create_async_engine(probe_url, echo=False)
    try:
        async with probe_engine.connect() as conn:
            await conn.execute(sa_text("SELECT 1"))
    finally:
        await probe_engine.dispose()

    # Single rolling backup at logger.db.bak — we don't keep history, just the
    # most recent pre-replace snapshot as a safety net. Older timestamped backups
    # (from a prior implementation) are intentionally not cleaned up here; if you
    # want them gone, delete them manually.
    backup_path: Path | None = None
    if DB_PATH.exists():
        backup_path = DB_PATH.with_suffix(DB_PATH.suffix + ".bak")
        shutil.copy2(DB_PATH, backup_path)

    # Dispose the engine pool so any new connection re-opens the new file.
    # Existing in-flight connections (none expected for a single user) will fail.
    await engine.dispose()

    # Swap. shutil.move handles the rename across same-filesystem cases.
    shutil.move(str(pending), str(DB_PATH))

    # Re-run schema migrations + seeding on the new file (idempotent — if the
    # uploaded DB is already up-to-date these all no-op).
    await init_db()

    return {
        "db_path": str(DB_PATH),
        "backup_path": str(backup_path) if backup_path else None,
        "bytes_written": len(new_bytes),
    }


async def export_db_bytes() -> bytes:
    """Read the current DB file off disk. Done synchronously inside a thread-safe
    read — SQLite's WAL mode (if enabled) handles concurrent readers, and we're
    not under write contention in a single-user app."""
    return DB_PATH.read_bytes()
