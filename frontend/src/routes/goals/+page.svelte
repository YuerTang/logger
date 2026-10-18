<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type GoalResponse, type DeliverableResponse } from '$lib/api/client';
	import GoalCard from '$lib/components/goals/GoalCard.svelte';
	import NextUp from '$lib/components/goals/NextUp.svelte';

	let goals = $state<GoalResponse[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	let creating = $state(false);
	let title = $state('');
	let deadline = $state('');
	let cats = $state('');
	let lines = $state('');

	async function load() {
		try {
			goals = await api.getGoals();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load goals';
		}
		loading = false;
	}

	function replace(g: GoalResponse) {
		goals = goals.map((x) => (x.id === g.id ? g : x));
	}

	async function toggle(d: DeliverableResponse) {
		replace(await api.updateDeliverable(d.id, { done: !d.done }));
	}

	// One deliverable per line, optional date at the end: "Pilot questionnaire 2026-10-24"
	function parseLines(text: string) {
		return text
			.split('\n')
			.map((l) => l.trim())
			.filter(Boolean)
			.map((l) => {
				const m = l.match(/^(.*?)[\s,·-]+(\d{4}-\d{2}-\d{2})$/);
				return m ? { title: m[1].trim(), due_date: m[2] } : { title: l, due_date: null };
			});
	}

	async function create() {
		if (!title.trim()) return;
		error = null;
		try {
			const g = await api.createGoal({
				title: title.trim(),
				deadline: deadline || null,
				categories: cats.split(',').map((s) => s.trim()).filter(Boolean),
				deliverables: parseLines(lines),
				position: goals.length
			});
			goals = [...goals, g];
			creating = false;
			title = deadline = cats = lines = '';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Could not create goal';
		}
	}

	let fileInput = $state<HTMLInputElement | null>(null);
	async function importFile(e: Event) {
		const f = (e.target as HTMLInputElement).files?.[0];
		if (!f) return;
		error = null;
		try {
			const data = JSON.parse(await f.text());
			goals = await api.importGoals(Array.isArray(data) ? data : [data]);
		} catch (err) {
			error = err instanceof Error ? `Import failed: ${err.message}` : 'Import failed';
		}
		if (fileInput) fileInput.value = '';
	}

	const behind = $derived(goals.filter((g) => g.status === 'behind').length);
	const input =
		'rounded-md border border-input bg-background px-2.5 py-1.5 text-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring';

	onMount(load);
</script>

<div class="mx-auto max-w-5xl space-y-6">
	<div class="flex flex-wrap items-end justify-between gap-3">
		<div>
			<h1 class="text-2xl font-bold">Goals</h1>
			<p class="mt-1 text-sm text-muted-foreground">
				What you're shipping, broken into deliverables with dates.
				{#if behind}<span class="text-red-600 dark:text-red-400">{behind} behind.</span>{/if}
			</p>
		</div>
		<div class="flex gap-2">
		<input type="file" accept=".json,application/json" class="hidden" bind:this={fileInput} onchange={importFile} />
		<button onclick={() => fileInput?.click()} class="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted">Import</button>
		<button onclick={() => (creating = !creating)} class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
			{creating ? 'Close' : 'New goal'}
		</button>
		</div>
	</div>

	{#if creating}
		<form class="space-y-3 rounded-xl border border-border bg-card p-5" onsubmit={(e) => { e.preventDefault(); create(); }}>
			<input class="{input} w-full" bind:value={title} placeholder="Goal, e.g. ESM → RSS 2027 submission" />
			<div class="flex flex-wrap gap-3">
				<label class="flex items-center gap-2 text-xs text-muted-foreground">Deadline <input type="date" class={input} bind:value={deadline} /></label>
				<label class="flex flex-1 items-center gap-2 text-xs text-muted-foreground">Categories (for time context)
					<input class="{input} flex-1" bind:value={cats} placeholder="ESM" />
				</label>
			</div>
			<textarea class="{input} h-32 w-full font-mono text-xs" bind:value={lines}
				placeholder={'One deliverable per line, date optional at the end:\nAction chunking controller working 2026-11-01\nFull Metaworld results table 2026-12-20\nPaper draft to Jiayuan'}></textarea>
			<button type="submit" disabled={!title.trim()} class="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-40">Create goal</button>
		</form>
	{/if}

	{#if error}<p class="text-sm text-destructive">{error}</p>{/if}

	{#if loading}
		<p class="text-sm text-muted-foreground">Loading…</p>
	{:else if goals.length === 0}
		<div class="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
			No goals yet. Start with what you need to ship and list the deliverables.
		</div>
	{:else}
		<section class="rounded-xl border border-border bg-card p-5">
			<h2 class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Next up</h2>
			<div class="mt-2"><NextUp {goals} limit={8} onToggle={toggle} /></div>
		</section>

		<div class="grid gap-4 lg:grid-cols-2">
			{#each goals as goal (goal.id)}
				<GoalCard {goal} onChange={replace} onDelete={(id) => (goals = goals.filter((g) => g.id !== id))} />
			{/each}
		</div>
	{/if}
</div>
