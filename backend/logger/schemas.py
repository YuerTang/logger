from pydantic import BaseModel


# ── Sessions ──────────────────────────────────────────────

class CategoryInCreate(BaseModel):
    name: str
    display_name: str | None = None
    family: str | None = None


class SessionCreate(BaseModel):
    year: int
    season: str
    label: str | None = None
    categories: list[CategoryInCreate] = []
    continue_from_session_id: int | None = None


class SessionUpdate(BaseModel):
    label: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_active: bool | None = None


class CategoryResponse(BaseModel):
    id: int
    session_id: int
    name: str
    display_name: str | None
    family_id: int | None
    family_name: str | None = None
    family_display_name: str | None = None
    family_type: str | None = None
    position: int
    total_minutes: int = 0

    model_config = {"from_attributes": True}


class SessionResponse(BaseModel):
    id: int
    year: int
    season: str
    label: str | None
    start_date: str | None
    end_date: str | None
    is_active: bool
    source_file: str | None
    created_at: str | None
    categories: list[CategoryResponse] = []
    total_minutes: int = 0
    days_logged: int = 0

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]


# ── Categories ────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str
    display_name: str | None = None
    family: str | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    display_name: str | None = None
    family_id: int | None = None


# ── Families ──────────────────────────────────────────────

class FamilyCreate(BaseModel):
    name: str
    display_name: str | None = None
    description: str | None = None
    color: str | None = None
    group_id: int | None = None
    family_type: str = "other"  # legacy — written for back-compat; group_id is preferred


class FamilyUpdate(BaseModel):
    name: str | None = None
    display_name: str | None = None
    description: str | None = None
    color: str | None = None
    group_id: int | None = None
    family_type: str | None = None  # legacy


class FamilyResponse(BaseModel):
    id: int
    name: str
    display_name: str | None
    description: str | None
    color: str | None
    group_id: int | None = None
    group_name: str | None = None
    group_display_name: str | None = None
    family_type: str | None  # legacy, kept for back-compat
    category_count: int = 0
    total_minutes: int = 0

    model_config = {"from_attributes": True}


# ── Family match rules ────────────────────────────────────

class FamilyMatchRuleCreate(BaseModel):
    family_id: int
    match_type: str  # "exact" | "prefix"
    pattern: str


class FamilyMatchRuleResponse(BaseModel):
    id: int
    family_id: int
    family_name: str | None = None
    family_display_name: str | None = None
    match_type: str
    pattern: str
    position: int

    model_config = {"from_attributes": True}


# ── Import ────────────────────────────────────────────────

class ImportCategoryPreview(BaseModel):
    name: str
    display_name: str | None = None
    auto_family_id: int | None
    family_display_name: str | None
    is_new_family: bool
    source_columns: list[str] = []


class ImportPreviewResponse(BaseModel):
    preview_id: str
    session_year: int
    session_season: str
    session_label: str
    row_count: int
    date_range: list[str]  # [min_date, max_date]
    categories: list[ImportCategoryPreview]
    text_row_count: int
    warnings: list[str]


class ImportConfirmRequest(BaseModel):
    preview_id: str


# ── Daily / Observations / Text ───────────────────────────

class ObservationResponse(BaseModel):
    id: int
    category_id: int
    category_name: str | None = None
    minutes: int
    source: str | None

    model_config = {"from_attributes": True}


class DailyRecordResponse(BaseModel):
    id: int
    session_id: int
    date: str
    day_of_week: str | None
    week_number: int | None
    total_minutes: int
    observations: list[ObservationResponse] = []

    model_config = {"from_attributes": True}


class TextEntryResponse(BaseModel):
    id: int
    session_id: int
    date: str
    location: str | None
    notes: str | None
    study_materials: str | None

    model_config = {"from_attributes": True}


# ── Settings ──────────────────────────────────────────────

class SettingResponse(BaseModel):
    key: str
    value: str

    model_config = {"from_attributes": True}


class SettingUpdate(BaseModel):
    value: str


class DBInfoResponse(BaseModel):
    db_path: str
    db_size_bytes: int
    session_count: int
    observation_count: int
    text_entry_count: int


# ── Timers ───────────────────────────────────────────────

class TimerStartRequest(BaseModel):
    category_id: int
    # Set when starting a timer from the Planner ("start what has been planned").
    plan_item_id: int | None = None


class TimerStopRequest(BaseModel):
    description: str | None = None
    location: str | None = None
    # Optional date override (YYYY-MM-DD). Used by the late-night attribution
    # prompt — when stopping a timer at 1am that should belong to "yesterday".
    override_date: str | None = None


class TimerEntryUpdate(BaseModel):
    category_id: int | None = None
    date: str | None = None
    duration_minutes: int | None = None
    description: str | None = None
    location: str | None = None


class TimerEntryResponse(BaseModel):
    id: int
    session_id: int
    category_id: int
    category_name: str | None = None
    date: str
    start_time: str
    end_time: str | None
    pause_start: str | None
    total_paused_seconds: int
    duration_minutes: int | None
    is_active: bool
    is_paused: bool
    description: str | None
    location: str | None
    plan_item_id: int | None = None
    plan_item_title: str | None = None

    model_config = {"from_attributes": True}


# ── Manual Entries ───────────────────────────────────────

class ManualEntryCreate(BaseModel):
    category_id: int
    date: str
    duration_minutes: int
    description: str | None = None
    location: str | None = None
    start_time: str | None = None
    # Set when logging time to close out a Planner item.
    plan_item_id: int | None = None


class ManualEntryUpdate(BaseModel):
    category_id: int | None = None
    date: str | None = None
    duration_minutes: int | None = None
    description: str | None = None
    location: str | None = None
    # ISO timestamp (UTC or with offset). Pass null to clear; omit to leave alone.
    start_time: str | None = None


class ManualEntryResponse(BaseModel):
    id: int
    session_id: int
    category_id: int
    category_name: str | None = None
    date: str
    duration_minutes: int
    description: str | None
    location: str | None
    # When the work actually happened (set by dragging the entry on the timeline).
    # null = unknown — UI infers start as created_at − duration.
    start_time: str | None = None
    created_at: str | None
    plan_item_id: int | None = None
    plan_item_title: str | None = None

    model_config = {"from_attributes": True}


# ── Daily Activity ───────────────────────────────────────

class DailyActivityResponse(BaseModel):
    date: str
    # The session this day belongs to — for past days that is an archived
    # session, not the active one.
    session_id: int | None = None
    session_label: str | None = None
    total_minutes: int
    timer_entries: list[TimerEntryResponse] = []
    manual_entries: list[ManualEntryResponse] = []
    observations: list[ObservationResponse] = []
    # Break marker for this date (neutral full-day rest/vacation label).
    is_break: bool = False
    break_label: str | None = None


class StreakResponse(BaseModel):
    current: int
    longest: int


# ── Break Days ───────────────────────────────────────────

class BreakDayCreate(BaseModel):
    start_date: str
    # Defaults to start_date (single day) when omitted.
    end_date: str | None = None
    label: str | None = None


class BreakDayResponse(BaseModel):
    id: int
    date: str
    label: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True}


# ── Planner ──────────────────────────────────────────────

class PlanItemCreate(BaseModel):
    title: str
    category_id: int
    start_date: str
    # Defaults to start_date (single-day item) when omitted.
    end_date: str | None = None
    # "HH:MM". Only kept if start_date == end_date — see planner_service.
    start_time: str | None = None
    end_time: str | None = None
    notes: str | None = None
    importance: str | None = None  # "low" | "medium" | "high"


class PlanItemUpdate(BaseModel):
    title: str | None = None
    category_id: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    # Pass "" to explicitly clear either time field; omit to leave alone.
    start_time: str | None = None
    end_time: str | None = None
    notes: str | None = None
    status: str | None = None  # "planned" | "done"
    # Pass "" to clear back to unset; omit to leave alone.
    importance: str | None = None


class PlanItemResponse(BaseModel):
    id: int
    title: str
    notes: str | None
    category_id: int
    category_name: str | None = None
    start_date: str
    end_date: str
    start_time: str | None
    end_time: str | None
    status: str
    importance: str | None = None
    timer_count: int = 0
    manual_count: int = 0
    logged_minutes: int = 0
    created_at: str | None = None
    notion_page_id: str | None = None

    model_config = {"from_attributes": True}


class PlanItemDetailResponse(PlanItemResponse):
    timer_entries: list[TimerEntryResponse] = []
    manual_entries: list[ManualEntryResponse] = []


# ── Groups (top-level semantic bucket) ──────────────────

class CategoryGroupCreate(BaseModel):
    name: str
    display_name: str | None = None
    description: str | None = None
    color: str | None = None


class CategoryGroupUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    color: str | None = None
    position: int | None = None


class CategoryGroupResponse(BaseModel):
    id: int
    name: str
    display_name: str | None
    description: str | None
    color: str | None
    position: int = 0
    is_system: bool = False
    family_count: int = 0
    total_minutes: int = 0


class GroupFamilyEntry(BaseModel):
    id: int
    name: str
    display_name: str | None = None
    color: str | None = None
    category_count: int = 0
    total_minutes: int = 0


class CategoryGroupDetailResponse(BaseModel):
    id: int
    name: str
    display_name: str | None
    description: str | None
    color: str | None
    position: int = 0
    is_system: bool = False
    families: list[GroupFamilyEntry] = []


class FamilyGroupAssignment(BaseModel):
    group_id: int | None  # None to detach


class BubbleCategoryData(BaseModel):
    category_id: int
    name: str
    merge_key: str
    session_id: int | None = None
    session_label: str | None = None
    total_minutes: int


class BubbleFamilyData(BaseModel):
    family_id: int
    name: str
    slug: str
    color: str | None
    total_minutes: int
    categories: list[BubbleCategoryData]


class BubbleGroupData(BaseModel):
    group_id: int | None
    name: str
    slug: str
    color: str | None
    families: list[BubbleFamilyData] = []
    ungrouped_categories: list[BubbleCategoryData] = []
    total_minutes: int


class BubbleDataResponse(BaseModel):
    groups: list[BubbleGroupData]
    total_minutes: int


# ── Batch Import ────────────────────────────────────────

class BatchImportRequest(BaseModel):
    data_dir: str | None = None


# ── Analytics ──────────────────────────────────────────

class AnalyticsOverviewResponse(BaseModel):
    total_minutes: int
    days_tracked: int
    daily_average: int
    active_categories: int


class DailyCategoryData(BaseModel):
    name: str
    minutes: int
    color: str | None = None


class DailySeriesPoint(BaseModel):
    date: str
    total_minutes: int
    categories: list[DailyCategoryData] = []


class CategoryBreakdownItem(BaseModel):
    name: str
    display_name: str | None
    family_name: str | None
    color: str | None
    total_minutes: int
    session_count: int
    session_label: str | None = None


class HeatmapPoint(BaseModel):
    date: str
    day_of_week: int  # 0=Mon, 6=Sun
    total_minutes: int


class SessionGroupData(BaseModel):
    name: str
    minutes: int
    color: str | None = None


class SessionComparisonItem(BaseModel):
    session_id: int
    label: str
    year: int
    season: str
    total_minutes: int
    days_logged: int
    groups: list[SessionGroupData] = []


# ── Chat ────────────────────────────────────────────────

class ChatQueryRequest(BaseModel):
    message: str


class ChatContextInfo(BaseModel):
    summary: str
    sessions_included: list[str]
    categories_included: list[str]
    date_range: list[str | None]
    data_points: int
    context_preview: str | None = None


class ChatApprovalResponse(BaseModel):
    approval_id: str
    user_message: str
    context_info: ChatContextInfo


class ChatApproveRequest(BaseModel):
    approval_id: str


class ChatMessageResponse(BaseModel):
    id: int | None = None
    role: str
    content: str
    created_at: str | None = None


class ChatStatusResponse(BaseModel):
    has_api_key: bool
    selected_model: str
    available_models: list[dict]


class ApiKeySaveRequest(BaseModel):
    api_key: str


# ── Projects ──────────────────────────────────────────

class ProjectSessionEntry(BaseModel):
    session_id: int
    session_label: str | None
    year: int
    season: str
    total_minutes: int
    active_days: int
    ai_description: str | None = None


class ProjectFamilyTimeline(BaseModel):
    family_id: int
    family_name: str
    display_name: str | None
    family_type: str | None
    color: str | None
    total_minutes: int
    sessions: list[ProjectSessionEntry] = []


class ProjectTimelineResponse(BaseModel):
    families: list[ProjectFamilyTimeline]
    sessions: list[dict]


class DescribeRequest(BaseModel):
    family_id: int
    session_id: int


class DescribeResponse(BaseModel):
    family_id: int
    session_id: int
    description: str


# ── Research Projects + GitHub ─────────────────────────

class GitHubRepoInfo(BaseModel):
    full_name: str
    name: str
    description: str | None = None
    language: str | None = None
    stars: int = 0
    html_url: str | None = None
    readme_excerpt: str | None = None
    recent_commits: list[dict] = []


class ResearchSessionEntry(BaseModel):
    session_id: int
    session_label: str | None
    year: int
    season: str
    total_minutes: int
    active_days: int
    ai_description: str | None = None
    text_entries_count: int = 0


class ResearchFamilyDetail(BaseModel):
    family_id: int
    family_name: str
    display_name: str | None
    color: str | None
    total_minutes: int
    sessions: list[ResearchSessionEntry] = []
    github_repos: list[GitHubRepoInfo] = []
    linked_repo_count: int = 0


class ResearchFamilyListItem(BaseModel):
    family_id: int
    family_name: str
    display_name: str | None
    color: str | None
    total_minutes: int
    session_count: int
    github_linked: bool = False


class ResearchFamiliesResponse(BaseModel):
    families: list[ResearchFamilyListItem]
    github_username: str | None = None


class GroupFamilyItem(BaseModel):
    family_id: int
    family_name: str
    display_name: str | None
    color: str | None
    total_minutes: int
    sessions: list[ResearchSessionEntry] = []
    github_repos: list[GitHubRepoInfo] = []
    linked_repo_count: int = 0


class GroupSummary(BaseModel):
    group_type: str
    label: str
    family_count: int
    total_minutes: int


class GroupDetailResponse(BaseModel):
    group_type: str
    label: str
    families: list[GroupFamilyItem]
    github_username: str | None = None


class GroupListResponse(BaseModel):
    groups: list[GroupSummary]
    github_username: str | None = None


class GitHubSearchResult(BaseModel):
    repos: list[GitHubRepoInfo]


class GitHubLinkRequest(BaseModel):
    family_id: int
    repo_full_name: str


class GitHubUnlinkRequest(BaseModel):
    family_id: int
    repo_full_name: str


class EnrichedDescribeRequest(BaseModel):
    family_id: int
    session_id: int
    include_github: bool = True


class EnrichedDescribeResponse(BaseModel):
    family_id: int
    session_id: int
    description: str
    github_context_used: bool = False
