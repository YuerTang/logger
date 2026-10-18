import type { DeliverableResponse, GoalStatus } from '$lib/api/client';

export function dueLabel(d: Pick<DeliverableResponse, 'days_until_due' | 'done' | 'due_date'>): string {
	if (d.due_date === null || d.days_until_due === null) return 'no date';
	const n = d.days_until_due;
	if (d.done) return shortDate(d.due_date);
	if (n < -1) return `${-n} days late`;
	if (n === -1) return '1 day late';
	if (n === 0) return 'today';
	if (n === 1) return 'tomorrow';
	if (n <= 6) return `in ${n} days`;
	return shortDate(d.due_date);
}

export function shortDate(ymd: string): string {
	const [y, m, d] = ymd.split('-').map(Number);
	return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function dueTone(d: Pick<DeliverableResponse, 'days_until_due' | 'done'>): string {
	if (d.done || d.days_until_due === null) return 'text-muted-foreground';
	if (d.days_until_due < 0) return 'text-red-600 dark:text-red-400 font-medium';
	if (d.days_until_due <= 2) return 'text-amber-600 dark:text-amber-400 font-medium';
	return 'text-muted-foreground';
}

export const STATUS: Record<GoalStatus, { label: string; cls: string }> = {
	on_track: { label: 'On track', cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' },
	due_soon: { label: 'Due soon', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
	behind: { label: 'Behind', cls: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
	done: { label: 'Done', cls: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400' }
};
