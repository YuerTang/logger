<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { api, type CategoryResponse, type PlanItemResponse } from '$lib/api/client';
	import { activeSession, loadActiveSession } from '$lib/stores/session';
	import { startPolling, stopPolling } from '$lib/stores/timer';
	import { todayYMD, todayYMDNow } from '$lib/stores/clock';
	import PlannerTimeline from '$lib/components/planner/PlannerTimeline.svelte';
	import PlanItemPanel from '$lib/components/planner/PlanItemPanel.svelte';
	import PlannerFilterBar, { type PlannerFilters, defaultPlannerFilters } from '$lib/components/planner/PlannerFilterBar.svelte';

	const WINDOW_BEFORE_DAYS = 7;
	const WINDOW_AFTER_DAYS = 28;
	const PAN_STEP_DAYS = 14;

	function ymdToDate(ymd: string): Date {
		const [y, m, d] = ymd.split('-').map(Number);
		return new Date(y, m - 1, d);
	}
	function dateToYmd(d: Date): string {
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
	}
	function addDays(ymd: string, n: number): string {
		const d = ymdToDate(ymd);
		return dateToYmd(new Date(d.getFullYear(), d.getMonth(), d.getDate() + n));
	}

	// Live current day (see stores/clock) — the planner is often left open for
	// long stretches, and "Today" must still mean today tomorrow.
	const today = $derived($todayYMD);
	// The visible window is only SEEDED from today; panning is user-driven from
	// there, so it deliberately takes a snapshot rather than tracking the store.
	let windowStart = $state(addDays(todayYMDNow(), -WINDOW_BEFORE_DAYS));
	let windowEnd = $state(addDays(todayYMDNow(), WINDOW_AFTER_DAYS));

	let categories = $state<CategoryResponse[]>([]);
	let items = $state<PlanItemResponse[]>([]);
	let loading = $state(true);
	let selectedItemId = $state<number | null>(null);
	let filters = $state<PlannerFilters>(defaultPlannerFilters());
	let notionReady = $state(false);
	let syncing = $state(false);
	let syncMsg = $state<string | null>(null);

	async function syncNotion() {
		syncing = true;
		syncMsg = null;
		try {
			const r = await api.syncNotion();
			syncMsg = r.created || r.updated || r.pushed_done || r.pushed_new
				? `${r.created} new · ${r.updated} updated · ${r.pushed_done + r.pushed_new} sent`
				: 'Up to date';
			await loadItems();
		} catch (e) {
			syncMsg = e instanceof Error ? e.message : 'Sync failed';
		}
		syncing = false;
		setTimeout(() => (syncMsg = null), 4000);
	}

	const filteredItems = $derived(
		items.filter((it) => {
			if (filters.categoryIds.size > 0 && !filters.categoryIds.has(it.category_id)) return false;
			if (filters.importance.size > 0 && !filters.importance.has(it.importance ?? 'none')) return false;
			if (filters.complete === 'done' && it.status !== 'done') return false;
			if (filters.complete === 'planned' && it.status !== 'planned') return false;
			return true;
		})
	);

	async function loadCategories() {
		const session = $activeSession;
		if (!session) return;
		try {
			categories = await api.getCategories(session.id);
		} catch { /* */ }
	}

	async function loadItems() {
		loading = true;
		try {
			items = await api.getPlanItems(windowStart, windowEnd);
		} catch { /* */ }
		loading = false;
	}

	$effect(() => {
		windowStart; windowEnd;
		loadItems();
	});

	function handlePan(direction: 'prev' | 'next' | 'today') {
		if (direction === 'today') {
			windowStart = addDays(today, -WINDOW_BEFORE_DAYS);
			windowEnd = addDays(today, WINDOW_AFTER_DAYS);
		} else {
			const delta = direction === 'prev' ? -PAN_STEP_DAYS : PAN_STEP_DAYS;
			windowStart = addDays(windowStart, delta);
			windowEnd = addDays(windowEnd, delta);
		}
	}

	async function handleCreate(data: { title: string; category_id: number; start_date: string; end_date: string; importance?: 'low' | 'medium' | 'high' }) {
		try {
			const item = await api.createPlanItem(data);
			await loadItems();
			selectedItemId = item.id;
		} catch (e: unknown) { console.error(e); }
	}

	async function handleDatesChange(id: number, start_date: string, end_date: string) {
		try {
			await api.updatePlanItem(id, { start_date, end_date });
			await loadItems();
		} catch (e: unknown) { console.error(e); }
	}

	onMount(async () => {
		await loadActiveSession();
		await loadCategories();
		try {
			const st = await api.getNotionStatus();
			notionReady = st.has_token && !!st.database_id;
			if (notionReady) syncNotion();
		} catch { /* */ }
		// The panel needs to know about already-running timers (e.g. one started
		// from the Dashboard) to show them inline instead of a stale "Start timer"
		// button — same store the Dashboard keeps warm via polling.
		startPolling();
	});

	onDestroy(() => {
		stopPolling();
	});
</script>

<div class="flex h-full min-h-0 flex-col gap-4">
	<div class="flex flex-wrap items-end justify-between gap-3">
		<div>
			<h1 class="text-2xl font-bold">Planner</h1>
			<p class="mt-1 text-sm text-muted-foreground">Plan itinerary items across days, then start or log time against them.</p>
		</div>
		{#if $activeSession}
			<div class="flex flex-wrap items-center gap-2">
				{#if notionReady}
					{#if syncMsg}<span class="text-xs text-muted-foreground">{syncMsg}</span>{/if}
					<button onclick={syncNotion} disabled={syncing}
						class="rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted disabled:opacity-50">
						{syncing ? 'Syncing…' : 'Sync Notion'}
					</button>
				{/if}
				<PlannerFilterBar {categories} {filters} onChange={(f) => (filters = f)} />
			</div>
		{/if}
	</div>

	{#if !$activeSession}
		<div class="rounded-lg border border-border bg-card p-8 text-center">
			<p class="text-muted-foreground">No active session. Go to <a href="/data" class="text-primary underline">Data</a> to activate or create a session.</p>
		</div>
	{:else}
		<div class="min-h-0 flex-1">
			<PlannerTimeline
				items={filteredItems}
				{categories}
				{windowStart}
				{windowEnd}
				onCreate={handleCreate}
				onDatesChange={handleDatesChange}
				onSelect={(id) => (selectedItemId = id)}
				onPan={handlePan}
			/>
		</div>
	{/if}
</div>

{#if selectedItemId !== null}
	<PlanItemPanel
		itemId={selectedItemId}
		{categories}
		onClose={() => (selectedItemId = null)}
		onChanged={loadItems}
	/>
{/if}
