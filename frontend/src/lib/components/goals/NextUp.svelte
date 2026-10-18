<script lang="ts">
	import type { GoalResponse, DeliverableResponse } from '$lib/api/client';
	import { dueLabel, dueTone } from './due';

	let {
		goals,
		limit = 6,
		onToggle,
		compact = false
	}: {
		goals: GoalResponse[];
		limit?: number;
		onToggle: (d: DeliverableResponse) => void;
		compact?: boolean;
	} = $props();

	// Every open deliverable across goals, earliest due first; undated last.
	const items = $derived(
		goals
			.flatMap((g) => g.deliverables.filter((d) => !d.done).map((d) => ({ d, goal: g.title })))
			.sort((a, b) => {
				const ad = a.d.due_date ?? '9999-99-99';
				const bd = b.d.due_date ?? '9999-99-99';
				return ad === bd ? a.d.position - b.d.position : ad < bd ? -1 : 1;
			})
			.slice(0, limit)
	);
</script>

{#if items.length === 0}
	<p class="text-sm text-muted-foreground">Nothing open. Add deliverables to a goal to see what's next.</p>
{:else}
	<ul class="divide-y divide-border">
		{#each items as { d, goal } (d.id)}
			<li class="flex items-center gap-3 {compact ? 'py-2' : 'py-2.5'}">
				<button
					onclick={() => onToggle(d)}
					aria-label="Mark done"
					class="flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded border border-input hover:border-primary hover:bg-primary/10 transition-colors"
				></button>
				<div class="min-w-0 flex-1">
					<div class="truncate text-sm">{d.title}</div>
					<div class="truncate text-xs text-muted-foreground">{goal}</div>
				</div>
				<span class="shrink-0 text-xs tabular-nums {dueTone(d)}">{dueLabel(d)}</span>
			</li>
		{/each}
	</ul>
{/if}
