from sqlalchemy import (
    Boolean, Column, Integer, Text, ForeignKey, UniqueConstraint, Index,
    text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, nullable=False)
    season = Column(Text, nullable=False)
    label = Column(Text)
    start_date = Column(Text)
    end_date = Column(Text)
    is_active = Column(Boolean, default=False)
    source_file = Column(Text)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (UniqueConstraint("year", "season"),)

    categories = relationship("Category", back_populates="session", cascade="all, delete-orphan")
    daily_records = relationship("DailyRecord", back_populates="session", cascade="all, delete-orphan")
    text_entries = relationship("TextEntry", back_populates="session", cascade="all, delete-orphan")


class CategoryFamily(Base):
    __tablename__ = "category_families"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False, unique=True)
    display_name = Column(Text)
    description = Column(Text)
    color = Column(Text)
    family_type = Column(Text, default="other")  # legacy — superseded by group_id; kept for compat
    group_id = Column(Integer, ForeignKey("category_groups.id", ondelete="SET NULL"))
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    categories = relationship("Category", back_populates="family")
    match_rules = relationship("FamilyMatchRule", back_populates="family", cascade="all, delete-orphan")
    group = relationship("CategoryGroup", back_populates="families")


class FamilyMatchRule(Base):
    __tablename__ = "family_match_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    family_id = Column(Integer, ForeignKey("category_families.id", ondelete="CASCADE"), nullable=False)
    match_type = Column(Text, nullable=False)  # "exact" | "prefix"
    pattern = Column(Text, nullable=False)     # lowercased
    position = Column(Integer, default=0)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        UniqueConstraint("match_type", "pattern"),
        Index("idx_family_match_rules_family", "family_id"),
        Index("idx_family_match_rules_lookup", "match_type", "pattern"),
    )

    family = relationship("CategoryFamily", back_populates="match_rules")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    display_name = Column(Text)
    family_id = Column(Integer, ForeignKey("category_families.id", ondelete="SET NULL"))
    position = Column(Integer, default=0)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        UniqueConstraint("session_id", "name"),
        Index("idx_categories_family", "family_id"),
        Index("idx_categories_session", "session_id"),
    )

    session = relationship("Session", back_populates="categories")
    family = relationship("CategoryFamily", back_populates="categories")
    observations = relationship("Observation", back_populates="category")


class DailyRecord(Base):
    __tablename__ = "daily_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    date = Column(Text, nullable=False)
    day_of_week = Column(Text)
    week_number = Column(Integer)
    total_minutes = Column(Integer, nullable=False, default=0)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        UniqueConstraint("session_id", "date"),
        Index("idx_daily_records_date", "date"),
        Index("idx_daily_records_session", "session_id"),
    )

    session = relationship("Session", back_populates="daily_records")
    observations = relationship("Observation", back_populates="daily_record", cascade="all, delete-orphan")


class Observation(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    daily_record_id = Column(Integer, ForeignKey("daily_records.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    minutes = Column(Integer, nullable=False, default=0)
    source = Column(Text, default="import")
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        UniqueConstraint("daily_record_id", "category_id"),
        Index("idx_observations_category", "category_id"),
        Index("idx_observations_daily", "daily_record_id"),
    )

    daily_record = relationship("DailyRecord", back_populates="observations")
    category = relationship("Category", back_populates="observations")


class TextEntry(Base):
    __tablename__ = "text_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    date = Column(Text, nullable=False)
    location = Column(Text)
    notes = Column(Text)
    study_materials = Column(Text)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        Index("idx_text_entries_date", "date"),
        Index("idx_text_entries_session", "session_id"),
    )

    session = relationship("Session", back_populates="text_entries")


class TimerEntry(Base):
    __tablename__ = "timer_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    date = Column(Text, nullable=False)
    start_time = Column(Text, nullable=False)
    end_time = Column(Text)
    pause_start = Column(Text)
    total_paused_seconds = Column(Integer, default=0)
    duration_minutes = Column(Integer)
    is_active = Column(Boolean, default=True)
    is_paused = Column(Boolean, default=False)
    description = Column(Text)
    location = Column(Text)
    # Set when this timer was started from the Planner ("start what has been
    # planned"). NULL for ordinary timers. SET NULL on plan deletion — the
    # logged time is real and stays, it just loses its plan attribution.
    plan_item_id = Column(Integer, ForeignKey("plan_items.id", ondelete="SET NULL"))
    created_at = Column(Text, server_default=text("(datetime('now'))"))
    updated_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        Index("idx_timer_active", "is_active", sqlite_where=text("is_active = 1")),
        Index("idx_timer_date", "date"),
        Index("idx_timer_category", "category_id"),
        Index("idx_timer_plan_item", "plan_item_id"),
    )


class ManualEntry(Base):
    __tablename__ = "manual_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    date = Column(Text, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    description = Column(Text)
    location = Column(Text)
    # When the work actually happened. created_at is when the user logged the
    # entry; start_time is when the work began. NULL = unknown (legacy / not yet
    # placed on the timeline). Set by dragging the entry on the Today Timeline.
    start_time = Column(Text)
    # Set when this entry was logged to close out a Planner item. NULL for
    # ordinary manual entries. SET NULL on plan deletion.
    plan_item_id = Column(Integer, ForeignKey("plan_items.id", ondelete="SET NULL"))
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        Index("idx_manual_date", "date"),
        Index("idx_manual_category", "category_id"),
        Index("idx_manual_plan_item", "plan_item_id"),
    )


class PlanItem(Base):
    """A planner itinerary item — a task scheduled for one or more future (or
    past) days, optionally with a specific time-of-day when it spans a single
    day. Starting a timer or logging a manual entry against a plan item links
    that entry back here (TimerEntry.plan_item_id / ManualEntry.plan_item_id)
    without marking the plan complete — a multi-day plan is expected to
    accumulate several logged sessions before the user explicitly marks it
    done (see planner_service.update_item)."""
    __tablename__ = "plan_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text, nullable=False)
    notes = Column(Text)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    start_date = Column(Text, nullable=False)   # YYYY-MM-DD
    end_date = Column(Text, nullable=False)     # YYYY-MM-DD; == start_date for single-day items
    # "HH:MM", 24h. Only meaningful (and only ever set) while start_date == end_date —
    # cleared whenever the item spans more than one day.
    start_time = Column(Text)
    end_time = Column(Text)
    status = Column(Text, nullable=False, default="planned")  # "planned" | "done"
    importance = Column(Text)  # "low" | "medium" | "high" | NULL (unset)
    # Notion sync (see services/notion_sync_service.py). NULL for items that
    # only exist in log(ger).
    notion_page_id = Column(Text)
    # Notion's last_edited_time as of our last sync — a different value on the
    # next pull means the task changed in Notion.
    notion_last_edited = Column(Text)
    # Our status as of the last sync — a different value means it changed here
    # and should be pushed to Notion's checkbox.
    notion_synced_status = Column(Text)
    created_at = Column(Text, server_default=text("(datetime('now'))"))
    updated_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        Index("idx_plan_items_range", "start_date", "end_date"),
        Index("idx_plan_items_category", "category_id"),
    )


class BreakDay(Base):
    """A rest / vacation / break day.

    Global (not session-scoped): a break is a personal day off independent of
    whichever academic session is active. Marking a day as a break does NOT add
    any time; it is a neutral marker that (1) renders as a full-day labeled block
    in the UI and (2) bridges the activity streak — work days on either side of a
    break stay connected, so taking a break never breaks your streak.
    """
    __tablename__ = "break_days"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Text, nullable=False, unique=True)  # YYYY-MM-DD
    label = Column(Text)                               # e.g. "Vacation", "Sick", "Rest"
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        Index("idx_break_days_date", "date"),
    )


class AIDescription(Base):
    __tablename__ = "ai_descriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    family_id = Column(Integer, ForeignKey("category_families.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    description = Column(Text, nullable=False)
    model_used = Column(Text)
    generated_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (UniqueConstraint("family_id", "session_id"),)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", Text)
    created_at = Column(Text, server_default=text("(datetime('now'))"))


class CategoryGroup(Base):
    """Top-level semantic group: Research, Training, Personal, Courses, ...

    Re-purposed from the prior auto-generated visualization-grouping role.
    A group contains one or more CategoryFamilies; each family contains
    one or more per-session Categories. The chain is: Group → Family → Category.
    """
    __tablename__ = "category_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False, unique=True)            # slug, e.g. "research"
    display_name = Column(Text)
    description = Column(Text)
    color = Column(Text)
    position = Column(Integer, default=0)
    is_system = Column(Boolean, default=False)                  # seeded vs user-added
    is_auto = Column(Boolean, default=False)                    # legacy column, retained for SQLite compat
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    families = relationship("CategoryFamily", back_populates="group")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(Text, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(Text, server_default=text("(datetime('now'))"))


class GitHubRepoCache(Base):
    __tablename__ = "github_repo_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(Text, nullable=False)
    repo_full_name = Column(Text, nullable=False)
    repo_name = Column(Text, nullable=False)
    description = Column(Text)
    readme_excerpt = Column(Text)
    recent_commits = Column(Text)  # JSON string
    language = Column(Text)
    stars = Column(Integer, default=0)
    html_url = Column(Text)
    fetched_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (UniqueConstraint("username", "repo_full_name"),)


class GitHubRepoLink(Base):
    __tablename__ = "github_repo_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    family_id = Column(Integer, ForeignKey("category_families.id", ondelete="CASCADE"), nullable=False)
    repo_full_name = Column(Text, nullable=False)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    __table_args__ = (
        UniqueConstraint("family_id", "repo_full_name"),
        Index("idx_github_links_family", "family_id"),
    )



class Goal(Base):
    """A goal defined by its deliverables, e.g. "Blackswan → CVPR 2027".

    Progress is judged by deliverables done against their due dates, not by
    hours. `categories` (JSON list of category names, matched across
    sessions) only links logged time to the goal so it can be shown as
    context."""
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text, nullable=False)
    deadline = Column(Text)  # YYYY-MM-DD, the final deliverable's date
    categories = Column(Text, nullable=False, default="[]")
    note = Column(Text)
    position = Column(Integer, default=0)
    archived = Column(Boolean, default=False)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    deliverables = relationship(
        "Deliverable", back_populates="goal", cascade="all, delete-orphan",
        order_by="Deliverable.position",
    )


class Deliverable(Base):
    """One concrete thing a goal needs, with a due date and a done state."""
    __tablename__ = "deliverables"

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_id = Column(Integer, ForeignKey("goals.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    due_date = Column(Text)  # YYYY-MM-DD
    done = Column(Boolean, default=False)
    done_at = Column(Text)
    note = Column(Text)
    position = Column(Integer, default=0)
    created_at = Column(Text, server_default=text("(datetime('now'))"))

    goal = relationship("Goal", back_populates="deliverables")
