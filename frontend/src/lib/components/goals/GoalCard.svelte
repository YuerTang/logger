<script lang="ts">
	import { api, type GoalResponse, type DeliverableResponse } from '$lib/api/client';
	import { dueLabel, dueTone, shortDate, STATUS } from './due';

	let {
		goal,
		onChange,
		onDelete
	}: {
		goal: GoalResponse;
		onChange: (g: GoalResponse) => void;
		onDelete: (id: number) => void;
	} = $props();

	let showDone = $state(false);
	let newTitle = $state('');
	let newDue = $state('');
	let editing = $state(false);
	let editTitle = $state('');
	let editDeadline = $state('');
	let editCats = $state('');
	let editNote = $state('');
	let editingDeliv = $state<number | null>(null);
	let delivTitle = $state('');
	let delivDue = $state('');
	let error = $state<string | null>(null);

	const open = $derived(goal.deliverables.filter((d) => !d.done));
	const done = $derived(goal.deliverables.filter((d) => d.done));
	const pct = $derived(goal.total_count ? Math.round((100 * goal.done_count) / goal.total_count) : 0);

	async function run(p: Promise<GoalResponse>) {
		error = null;
		try {
			onChange(await p);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Something went wrong';
		}
	}

	const toggle = (d: DeliverableResponse) => run(api.updateDeliverable(d.id, { done: !d.done }));

	async function add() {
		if (!newTitle.trim()) return;
		await run(api.addDeliverable(goal.id, { title: newTitle.trim(), due_date: newDue || null }));
		newTitle = '';
		newDue = '';
	}

	function startEdit() {
		editTitle = goal.title;
		editDeadline = goal.deadline ?? '';
		editCats = goal.categories.join(', ');
		editNote = goal.note ?? '';
		editing = true;
	}

	async function saveEdit() {
		await run(
			api.updateGoal(goal.id, {
				title: editTitle,
				deadline: editDeadline || null,
				categories: editCats.split(',').map((s) => s.trim()).filter(Boolean),
				note: editNote || null
			})
		);
		editing = false;
	}

	function startDeliv(d: DeliverableResponse) {
		editingDeliv = d.id;
		delivTitle = d.title;
		delivDue = d.due_date ?? '';
	}

	async function saveDeliv(id: number) {
		await run(api.updateDeliverable(id, { title: delivTitle, due_date: delivDue || null }));
		editingDeliv = null;
	}

	async function removeGoal() {
		if (!confirm(`Delete "${goal.title}" and its deliverables?`)) return;
		await api.deleteGoal(goal.id);
		onDelete(goal.id);
	}

	const input =
		'rounded-md border border-input bg-background px-2.5 py-1.5 text-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring';
</script>

<article class="rounded-xl border border-border bg-card p-5">
	{#if editing}
		<div class="space-y-2">
			<input class="{input} w-full font-semibold" bind:value={editTitle} placeholder="Goal" />
			<div class="flex flex-wrap gap-2">
				<label class="flex items-center gap-2 text-xs text-muted-foreground">
					Deadline <input type="date" class={input} bind:value={editDeadline} />
				</label>
				<label class="flex flex-1 items-center gap-2 text-xs text-muted-foreground">
					Categories <input class="{input} flex-1" bind:value={editCats} placeholder="Blackswan, ESM" />
				</label>
			</div>
			<input class="{input} w-full" bind:value={editNote} placeholder="Note (optional)" />
			<div class="flex gap-2">
				<button onclick={saveEdit} class="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90">Save</button>
				<button onclick={() => (editing = false)} class="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted">Cancel</button>
				<button onclick={removeGoal} class="ml-auto text-xs text-destructive hover:underline">Delete goal</button>
			</div>
		</div>
	{:else}
		<header class="flex items-start justify-between gap-3">
			<div class="min-w-0">
				<h2 class="text-base font-semibold leading-snug">{goal.title}</h2>
				<p class="mt-0.5 text-xs text-muted-foreground">
					{#if goal.deadline}
						{shortDate(goal.deadline)}
						{#if goal.days_left !== null}
							· {goal.days_left > 0 ? `${goal.days_left} days left` : goal.days_left === 0 ? 'today' : `${-goal.days_left} days ago`}
						{/if}
					{:else}
						No deadline
					{/if}
					{#if goal.categories.length}
						· {goal.time.week_hours}h this week
					{/if}
				</p>
				{#if goal.note}<p class="mt-1 text-xs text-muted-foreground">{goal.note}</p>{/if}
			</div>
			<div class="flex shrink-0 items-center gap-2">
				<span class="rounded-full px-2.5 py-0.5 text-xs font-medium {STATUS[goal.status].cls}">
					{STATUS[goal.status].label}{goal.overdue_count > 1 ? ` · ${goal.overdue_count}` : ''}
				</span>
				<button onclick={startEdit} aria-label="Edit goal" class="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground">
					<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.75"><path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536M9 13l6.232-6.232a2.5 2.5 0 113.536 3.536L12.536 16.5H9V13z" /></svg>
				</button>
			</div>
		</header>
	{/if}

	<div class="mt-4 flex items-center gap-3">
		<div class="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
			<div class="h-full rounded-full bg-primary transition-all" style="width: {pct}%"></div>
		</div>
		<span class="text-xs tabular-nums text-muted-foreground">{goal.done_count}/{goal.total_count}</span>
	</div>

	<ul class="mt-3 divide-y divide-border">
		{#each open as d (d.id)}
			<li class="flex items-center gap-3 py-2">
				<button
					onclick={() => toggle(d)}
					aria-label="Mark done"
					class="h-4 w-4 shrink-0 rounded border border-input hover:border-primary hover:bg-primary/10"
				></button>
				{#if editingDeliv === d.id}
					<input class="{input} min-w-0 flex-1" bind:value={delivTitle} onkeydown={(e) => e.key === 'Enter' && saveDeliv(d.id)} />
					<input type="date" class={input} bind:value={delivDue} />
					<button onclick={() => saveDeliv(d.id)} class="text-xs font-medium text-primary">Save</button>
					<button onclick={() => run(api.deleteDeliverable(d.id))} class="text-xs text-destructive">Delete</button>
				{:else}
					<button class="min-w-0 flex-1 truncate text-left text-sm hover:underline" onclick={() => startDeliv(d)}>{d.title}</button>
					<span class="shrink-0 text-xs tabular-nums {dueTone(d)}">{dueLabel(d)}</span>
				{/if}
			</li>
		{/each}
	</ul>

	<form class="mt-2 flex gap-2" onsubmit={(e) => { e.preventDefault(); add(); }}>
		<input class="{input} min-w-0 flex-1" bind:value={newTitle} placeholder="Add a deliverable" />
		<input type="date" class={input} bind:value={newDue} />
		<button type="submit" disabled={!newTitle.trim()} class="rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40">Add</button>
	</form>

	{#if done.length}
		<button onclick={() => (showDone = !showDone)} class="mt-3 text-xs text-muted-foreground hover:text-foreground">
			{showDone ? 'Hide' : 'Show'} {done.length} done
		</button>
		{#if showDone}
			<ul class="mt-1 divide-y divide-border">
				{#each done as d (d.id)}
					<li class="flex items-center gap-3 py-1.5">
						<button onclick={() => toggle(d)} aria-label="Mark not done" class="flex h-4 w-4 shrink-0 items-center justify-center rounded border border-primary bg-primary text-primary-foreground">
							<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="3"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" /></svg>
						</button>
						<span class="min-w-0 flex-1 truncate text-sm text-muted-foreground line-through">{d.title}</span>
					</li>
				{/each}
			</ul>
		{/if}
	{/if}

	{#if error}<p class="mt-2 text-xs text-destructive">{error}</p>{/if}
</article>
