<script lang="ts">
	import { onMount } from 'svelte';
	import { theme } from '$lib/stores/theme';
	import { api, type DBInfoResponse, type ChatStatusResponse, type SettingResponse, type NotionStatus, type NotionSyncResult } from '$lib/api/client';
	import { timezone, COMMON_TIMEZONES, DEFAULT_TIMEZONE } from '$lib/stores/timezone';

	let dbInfo = $state<DBInfoResponse | null>(null);
	let apiKey = $state('');
	let chatStatusData = $state<ChatStatusResponse | null>(null);
	let saveMessage = $state<string | null>(null);
	let saving = $state(false);

	// Database replace/download
	let dbReplaceInput = $state<HTMLInputElement | null>(null);
	let dbReplacing = $state(false);
	let dbMessage = $state<string | null>(null);
	let dbMessageIsError = $state(false);
	let pendingReplaceFile = $state<File | null>(null);

	// Timezone selection
	let selectedTz = $state<string>(DEFAULT_TIMEZONE);
	let tzMessage = $state<string | null>(null);
	let tzSaving = $state(false);
	const tzKnownIds = COMMON_TIMEZONES.map((t) => t.id);
	const isCustomTz = $derived(!tzKnownIds.includes(selectedTz));

	async function handleSaveTimezone(value: string) {
		tzSaving = true;
		tzMessage = null;
		try {
			await api.updateSetting('timezone', value);
			timezone.set(value);
			selectedTz = value;
			tzMessage = 'Timezone saved';
			setTimeout(() => (tzMessage = null), 2500);
		} catch (e) {
			tzMessage = e instanceof Error ? e.message : 'Failed to save timezone';
		} finally {
			tzSaving = false;
		}
	}

	// Notion
	let notion = $state<NotionStatus | null>(null);
	let notionToken = $state('');
	let notionDb = $state('');
	let notionRules = $state<{ match: string; category: string }[]>([]);
	let notionDefault = $state('');
	let notionBusy = $state(false);
	let notionMsg = $state<string | null>(null);
	let notionMsgErr = $state(false);
	let notionResult = $state<NotionSyncResult | null>(null);

	function applyNotion(st: NotionStatus) {
		notion = st;
		notionDb = st.database_id ?? '';
		notionRules = st.rules.length ? st.rules.map((r) => ({ ...r })) : [{ match: '', category: '' }];
		notionDefault = st.default_category ?? '';
		notionResult = st.last_result;
	}

	async function notionDo(fn: () => Promise<string | void>) {
		notionBusy = true;
		notionMsg = null;
		notionMsgErr = false;
		try {
			const msg = await fn();
			if (msg) notionMsg = msg;
		} catch (e) {
			notionMsg = e instanceof Error ? e.message : 'Something went wrong';
			notionMsgErr = true;
		} finally {
			notionBusy = false;
		}
	}

	const saveNotionToken = () =>
		notionDo(async () => {
			applyNotion(await api.saveNotionToken(notionToken.trim()));
			notionToken = '';
			return 'Token saved';
		});

	const saveNotionConfig = () =>
		notionDo(async () => {
			applyNotion(
				await api.saveNotionConfig({
					database: notionDb,
					rules: notionRules.filter((r) => r.match.trim() && r.category.trim()),
					default_category: notionDefault
				})
			);
			const t = await api.testNotion();
			return t.missing_properties.length
				? `Connected to "${t.title}", but it's missing: ${t.missing_properties.join(', ')}`
				: `Connected to "${t.title}"`;
		});

	const toggleNotionPush = () =>
		notionDo(async () => {
			applyNotion(await api.saveNotionConfig({ push_new: !notion?.push_new }));
		});

	const runNotionSync = () =>
		notionDo(async () => {
			notionResult = await api.syncNotion();
			notion = await api.getNotionStatus();
			const r = notionResult;
			return `Synced: ${r.created} new, ${r.updated} updated, ${r.pushed_done + r.pushed_new} sent to Notion`;
		});

	// GitHub
	let githubUsername = $state('');
	let savedGithubUsername = $state<string | null>(null);
	let githubToken = $state('');
	let hasGithubToken = $state(false);
	let githubPublicOnly = $state(false);
	let githubSaving = $state(false);
	let githubMessage = $state<string | null>(null);

	onMount(async () => {
		try {
			const [db, status, settings] = await Promise.all([
				api.getDBInfo(),
				api.getChatStatus(),
				api.getSettings()
			]);
			dbInfo = db;
			chatStatusData = status;
			api.getNotionStatus().then(applyNotion).catch(() => {});
			const ghSetting = settings.find((s: SettingResponse) => s.key === 'github_username');
			if (ghSetting) {
				savedGithubUsername = ghSetting.value;
				githubUsername = ghSetting.value;
			}
			const ghToken = settings.find((s: SettingResponse) => s.key === 'github_token');
			if (ghToken && ghToken.value) {
				hasGithubToken = true;
			}
			const ghPublic = settings.find((s: SettingResponse) => s.key === 'github_public_only');
			if (ghPublic && ghPublic.value === 'true') {
				githubPublicOnly = true;
			}
			const tzSetting = settings.find((s: SettingResponse) => s.key === 'timezone');
			selectedTz = tzSetting?.value || DEFAULT_TIMEZONE;
			timezone.set(selectedTz);
		} catch {
			// API not available
		}
	});

	function formatBytes(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function setTheme(value: string) {
		theme.set(value as 'light' | 'dark' | 'system');
	}

	async function handleSaveKey() {
		if (!apiKey.trim()) return;
		saving = true;
		saveMessage = null;
		try {
			await api.saveApiKey(apiKey);
			chatStatusData = await api.getChatStatus();
			apiKey = '';
			saveMessage = 'API key saved successfully';
			setTimeout(() => (saveMessage = null), 3000);
		} catch (e) {
			saveMessage = e instanceof Error ? e.message : 'Failed to save';
		} finally {
			saving = false;
		}
	}

	async function handleDeleteKey() {
		try {
			await api.deleteApiKey();
			chatStatusData = await api.getChatStatus();
			saveMessage = 'API key removed';
			setTimeout(() => (saveMessage = null), 3000);
		} catch (e) {
			saveMessage = e instanceof Error ? e.message : 'Failed to remove';
		}
	}

	async function handleSaveGithub() {
		if (!githubUsername.trim()) return;
		githubSaving = true;
		githubMessage = null;
		try {
			await api.updateSetting('github_username', githubUsername.trim());
			savedGithubUsername = githubUsername.trim();
			githubMessage = 'GitHub username saved';
			setTimeout(() => (githubMessage = null), 3000);
		} catch (e) {
			githubMessage = e instanceof Error ? e.message : 'Failed to save';
		} finally {
			githubSaving = false;
		}
	}

	async function handleTogglePublicOnly() {
		githubPublicOnly = !githubPublicOnly;
		try {
			await api.updateSetting('github_public_only', githubPublicOnly ? 'true' : 'false');
			await api.clearGithubCache().catch(() => {});
			githubMessage = githubPublicOnly ? 'Switched to public repos only' : 'Token enabled — private repos accessible';
			setTimeout(() => (githubMessage = null), 3000);
		} catch {
			githubPublicOnly = !githubPublicOnly; // revert
		}
	}

	async function handleSaveToken() {
		if (!githubToken.trim()) return;
		githubSaving = true;
		githubMessage = null;
		try {
			await api.updateSetting('github_token', githubToken.trim());
			// Clear repo cache so next search uses the new token
			await api.clearGithubCache().catch(() => {});
			hasGithubToken = true;
			githubToken = '';
			githubMessage = 'Token saved — private repos now accessible';
			setTimeout(() => (githubMessage = null), 3000);
		} catch (e) {
			githubMessage = e instanceof Error ? e.message : 'Failed to save';
		} finally {
			githubSaving = false;
		}
	}

	async function handleRemoveToken() {
		githubSaving = true;
		githubMessage = null;
		try {
			await api.updateSetting('github_token', '');
			hasGithubToken = false;
			githubMessage = 'Token removed';
			setTimeout(() => (githubMessage = null), 3000);
		} catch (e) {
			githubMessage = e instanceof Error ? e.message : 'Failed to remove';
		} finally {
			githubSaving = false;
		}
	}

	async function handleRemoveGithub() {
		githubSaving = true;
		githubMessage = null;
		try {
			await api.updateSetting('github_username', '');
			savedGithubUsername = null;
			githubUsername = '';
			githubMessage = 'GitHub username removed';
			setTimeout(() => (githubMessage = null), 3000);
		} catch (e) {
			githubMessage = e instanceof Error ? e.message : 'Failed to remove';
		} finally {
			githubSaving = false;
		}
	}

	function flashDbMessage(msg: string, isError = false) {
		dbMessage = msg;
		dbMessageIsError = isError;
		if (!isError) setTimeout(() => (dbMessage = null), 4000);
	}

	function pickReplaceFile() {
		dbReplaceInput?.click();
	}

	function onReplaceFileChosen(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		input.value = ''; // allow re-selecting the same file
		if (!file) return;
		if (!file.name.toLowerCase().endsWith('.db') && !file.name.toLowerCase().endsWith('.sqlite')) {
			flashDbMessage('Please choose a .db or .sqlite file', true);
			return;
		}
		pendingReplaceFile = file;
		dbMessage = null;
	}

	async function confirmReplaceDB() {
		if (!pendingReplaceFile) return;
		dbReplacing = true;
		dbMessage = null;
		try {
			const res = await api.replaceDB(pendingReplaceFile);
			pendingReplaceFile = null;
			dbInfo = await api.getDBInfo();
			flashDbMessage(
				res.backup_path
					? `Database replaced. Previous DB backed up to ${res.backup_path.split('/').pop()}.`
					: 'Database replaced.'
			);
		} catch (e) {
			flashDbMessage(e instanceof Error ? e.message : 'Replace failed', true);
		} finally {
			dbReplacing = false;
		}
	}

	function cancelReplace() {
		pendingReplaceFile = null;
		dbMessage = null;
	}

	async function handleDownloadDB() {
		try {
			const blob = await api.downloadDB();
			const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = `logger-${ts}.db`;
			a.click();
			URL.revokeObjectURL(url);
		} catch (e) {
			flashDbMessage(e instanceof Error ? e.message : 'Download failed', true);
		}
	}

	function formatPath(path: string): string {
		// Replace home dir with ~ for readability
		return path.replace(/^\/Users\/[^/]+/, '~');
	}

	async function handleModelChange(modelId: string) {
		try {
			await api.setChatModel(modelId);
			if (chatStatusData) {
				chatStatusData = { ...chatStatusData, selected_model: modelId };
			}
		} catch {
			// ignore
		}
	}
</script>

<div class="mx-auto max-w-2xl space-y-8">
	<h1 class="text-2xl font-bold">Settings</h1>

	<!-- Appearance -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold">Appearance</h2>
		<div class="rounded-lg border border-border bg-card p-5">
			<span class="text-sm font-medium">Theme</span>
			<div class="mt-2 flex gap-2">
				{#each ['light', 'dark', 'system'] as opt}
					<button
						onclick={() => setTheme(opt)}
						class="rounded-lg border px-4 py-2 text-sm font-medium transition-colors
							{$theme === opt
								? 'border-primary bg-primary/10 text-primary'
								: 'border-border text-muted-foreground hover:bg-muted'}"
					>
						{opt.charAt(0).toUpperCase() + opt.slice(1)}
					</button>
				{/each}
			</div>
		</div>
	</section>

	<!-- Timezone -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold">Timezone</h2>
		<div class="space-y-3 rounded-lg border border-border bg-card p-5">
			<div class="flex items-center justify-between gap-2">
				<span class="text-sm font-medium">Display timezone</span>
				<span class="rounded-full bg-muted px-2.5 py-0.5 text-xs font-mono">{$timezone}</span>
			</div>
			<p class="text-xs text-muted-foreground">
				Clock times shown in the dashboard log, late-night prompt, and date picker are formatted in this timezone.
				Stored UTC timestamps in the DB are unchanged.
			</p>
			<select
				bind:value={selectedTz}
				onchange={(e) => handleSaveTimezone((e.currentTarget as HTMLSelectElement).value)}
				disabled={tzSaving}
				class="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
			>
				{#each COMMON_TIMEZONES as opt}
					<option value={opt.id}>{opt.label} — {opt.id}</option>
				{/each}
				{#if isCustomTz}
					<option value={selectedTz}>{selectedTz} (custom)</option>
				{/if}
			</select>
			<details class="text-xs text-muted-foreground">
				<summary class="cursor-pointer hover:text-foreground">Use a different IANA timezone</summary>
				<div class="mt-2 flex gap-2">
					<input
						type="text"
						placeholder="e.g. America/Phoenix"
						class="flex-1 rounded-md border border-input bg-background px-2.5 py-1.5 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
						onkeydown={(e) => {
							if (e.key === 'Enter') {
								const v = (e.currentTarget as HTMLInputElement).value.trim();
								if (v) handleSaveTimezone(v);
							}
						}}
					/>
					<span class="self-center text-[10px]">Enter to apply</span>
				</div>
			</details>
			{#if tzMessage}
				<p class="text-xs {tzMessage.toLowerCase().includes('saved') ? 'text-green-600 dark:text-green-400' : 'text-destructive'}">
					{tzMessage}
				</p>
			{/if}
		</div>
	</section>

	<!-- AI Configuration -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold">AI Configuration</h2>
		<div class="rounded-lg border border-border bg-card p-5 space-y-4">
			<!-- Status badge -->
			<div class="flex items-center justify-between">
				<span class="text-sm font-medium">Claude API Key</span>
				{#if chatStatusData}
					{#if chatStatusData.has_api_key}
						<span class="flex items-center gap-1.5 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
							<span class="h-1.5 w-1.5 rounded-full bg-green-500"></span>
							Connected
						</span>
					{:else}
						<span class="flex items-center gap-1.5 rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-700 dark:bg-red-900/30 dark:text-red-400">
							<span class="h-1.5 w-1.5 rounded-full bg-red-500"></span>
							Not configured
						</span>
					{/if}
				{/if}
			</div>

			<p class="text-xs text-muted-foreground">Required for Chat and Project descriptions</p>

			<div class="flex gap-2">
				<input
					id="api-key"
					type="password"
					bind:value={apiKey}
					placeholder="sk-ant-..."
					class="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
				/>
				<button
					onclick={handleSaveKey}
					disabled={!apiKey.trim() || saving}
					class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
				>
					{saving ? 'Saving...' : 'Save'}
				</button>
			</div>

			{#if chatStatusData?.has_api_key}
				<button
					onclick={handleDeleteKey}
					class="text-xs text-destructive hover:underline"
				>
					Remove API key
				</button>
			{/if}

			{#if saveMessage}
				<p class="text-xs {saveMessage.includes('success') || saveMessage.includes('removed') ? 'text-green-600 dark:text-green-400' : 'text-destructive'}">
					{saveMessage}
				</p>
			{/if}

			<!-- Model selector -->
			{#if chatStatusData}
				<div class="border-t border-border pt-4">
					<label for="model-select" class="text-sm font-medium">Chat Model</label>
					<p class="text-xs text-muted-foreground mt-0.5 mb-2">Select which Claude model to use for chat</p>
					<select
						id="model-select"
						onchange={(e) => handleModelChange((e.target as HTMLSelectElement).value)}
						class="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
					>
						{#each chatStatusData.available_models as model}
							<option value={model.id} selected={model.id === chatStatusData.selected_model}>
								{model.name}
							</option>
						{/each}
					</select>
				</div>
			{/if}
		</div>
	</section>

	<!-- GitHub Integration -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold">Notion Sync</h2>
		<div class="rounded-lg border border-border bg-card p-5 space-y-5">
			<p class="text-xs text-muted-foreground">
				Brings dated tasks from your Notion task database into the Planner, and checks them off in Notion when you mark them done here. Syncs every 10 minutes while the app is open.
			</p>

			<!-- Token -->
			<div class="space-y-2">
				<div class="flex items-center justify-between">
					<span class="text-sm font-medium">Integration token</span>
					<span class="rounded-full px-2.5 py-0.5 text-xs font-medium {notion?.has_token ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' : 'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400'}">
						{notion?.has_token ? 'Saved' : 'Not set'}
					</span>
				</div>
				<p class="text-xs text-muted-foreground">
					Create one at notion.so/profile/integrations (Internal), then in Notion open your task database's page, ••• → Connections, and add it.
				</p>
				<div class="flex gap-2">
					<input type="password" bind:value={notionToken} placeholder="ntn_… or secret_…"
						class="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring" />
					<button onclick={saveNotionToken} disabled={!notionToken.trim() || notionBusy}
						class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">Save</button>
				</div>
				{#if notion?.has_token}
					<button onclick={() => notionDo(async () => { applyNotion(await api.deleteNotionToken()); return 'Token removed'; })} class="text-xs text-destructive hover:underline">Remove token</button>
				{/if}
			</div>

			<!-- Database + mapping -->
			<div class="space-y-3 border-t border-border pt-4">
				<label class="block space-y-1">
					<span class="text-sm font-medium">Task database</span>
					<input bind:value={notionDb} placeholder="Paste the database link or ID"
						class="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring" />
					<span class="block text-xs text-muted-foreground">Expects properties Name (title), When (date), Complete (checkbox), Projects (relation).</span>
				</label>

				<div class="space-y-2">
					<span class="text-sm font-medium">Category rules</span>
					<p class="text-xs text-muted-foreground">
						Tasks whose title or project contains a category's name (e.g. "EE 227" → EE227) are matched automatically. Add rules for the rest, e.g. project "Life Admin" → Logistics.
					</p>
					{#each notionRules as rule, i}
						<div class="flex items-center gap-2">
							<input bind:value={rule.match} placeholder="Text or project name"
								class="min-w-0 flex-1 rounded-md border border-input bg-background px-2.5 py-1.5 text-sm" />
							<span class="text-xs text-muted-foreground">→</span>
							<input bind:value={rule.category} placeholder="Category"
								class="w-36 rounded-md border border-input bg-background px-2.5 py-1.5 text-sm" />
							<button onclick={() => (notionRules = notionRules.filter((_, j) => j !== i))} class="text-xs text-muted-foreground hover:text-destructive" aria-label="Remove rule">✕</button>
						</div>
					{/each}
					<button onclick={() => (notionRules = [...notionRules, { match: '', category: '' }])} class="text-xs text-primary hover:underline">+ Add rule</button>
				</div>

				<label class="flex items-center gap-2">
					<span class="text-sm">Anything else goes to</span>
					<input bind:value={notionDefault} placeholder="(skip it)"
						class="w-40 rounded-md border border-input bg-background px-2.5 py-1.5 text-sm" />
				</label>

				<button onclick={saveNotionConfig} disabled={!notion?.has_token || !notionDb.trim() || notionBusy}
					class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
					Save &amp; test connection
				</button>
			</div>

			<!-- Push + sync -->
			<div class="space-y-3 border-t border-border pt-4">
				<div class="flex items-center justify-between">
					<div>
						<div class="text-sm font-medium">Send new Planner items to Notion</div>
						<div class="text-xs text-muted-foreground">Items you plan here also show up in your Notion task list.</div>
					</div>
					<button onclick={toggleNotionPush} disabled={notionBusy} aria-label="Toggle sending new items"
						class="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors {notion?.push_new ? 'bg-primary' : 'bg-muted-foreground/30'}">
						<span class="pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform {notion?.push_new ? 'translate-x-4' : 'translate-x-0'}"></span>
					</button>
				</div>
				<div class="flex items-center gap-3">
					<button onclick={runNotionSync} disabled={!notion?.has_token || !notion?.database_id || notionBusy}
						class="rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50">
						{notionBusy ? 'Working…' : 'Sync now'}
					</button>
					{#if notion?.last_sync}
						<span class="text-xs text-muted-foreground">Last sync {new Date(notion.last_sync).toLocaleString()}</span>
					{/if}
				</div>
				{#if notionResult?.unmatched?.length}
					<p class="text-xs text-amber-600 dark:text-amber-400">
						Skipped (no category): {notionResult.unmatched.join(', ')}. Add a rule or a fallback category.
					</p>
				{/if}
				{#if notionResult?.errors?.length}
					<p class="text-xs text-destructive">{notionResult.errors.join(' · ')}</p>
				{/if}
			</div>

			{#if notionMsg}
				<p class="text-xs {notionMsgErr ? 'text-destructive' : 'text-muted-foreground'}">{notionMsg}</p>
			{/if}
		</div>
	</section>

	<section class="space-y-4">
		<h2 class="text-lg font-semibold">GitHub Integration</h2>
		<div class="rounded-lg border border-border bg-card p-5 space-y-4">
			<div class="flex items-center justify-between">
				<span class="text-sm font-medium">GitHub Username</span>
				{#if savedGithubUsername}
					<span class="flex items-center gap-1.5 rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
						@{savedGithubUsername}
					</span>
				{:else}
					<span class="flex items-center gap-1.5 rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
						Not set
					</span>
				{/if}
			</div>

			<p class="text-xs text-muted-foreground">
				Used to enrich research project descriptions with GitHub repo data
			</p>

			<div class="flex gap-2">
				<input
					type="text"
					bind:value={githubUsername}
					placeholder="your-username"
					class="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
				/>
				<button
					onclick={handleSaveGithub}
					disabled={!githubUsername.trim() || githubSaving}
					class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
				>
					{githubSaving ? 'Saving...' : 'Save'}
				</button>
			</div>

			{#if savedGithubUsername}
				<button
					onclick={handleRemoveGithub}
					class="text-xs text-destructive hover:underline"
				>
					Remove username
				</button>
			{/if}

			<!-- Repo access mode -->
			<div class="border-t border-border pt-4">
				<div class="flex items-center justify-between">
					<span class="text-sm font-medium">Repo Access</span>
					<div class="flex items-center gap-2">
						<button
							onclick={handleTogglePublicOnly}
							class="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors {githubPublicOnly ? 'bg-muted-foreground/30' : 'bg-primary'}"
						>
							<span
								class="pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform {githubPublicOnly ? 'translate-x-0' : 'translate-x-4'}"
							></span>
						</button>
						<span class="text-xs text-muted-foreground">
							{githubPublicOnly ? 'Public repos only' : 'Include private repos'}
						</span>
					</div>
				</div>
				<p class="text-xs text-muted-foreground mt-1">
					{githubPublicOnly
						? 'Only public repos are shown. No token needed.'
						: 'Uses your token to access private repos and repos you contribute to.'}
				</p>
			</div>

			<!-- Personal Access Token (hidden in public-only mode) -->
			{#if !githubPublicOnly}
				<div class="border-t border-border pt-4">
					<div class="flex items-center justify-between">
						<span class="text-sm font-medium">Personal Access Token</span>
						{#if hasGithubToken}
							<span class="flex items-center gap-1.5 rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
								<span class="h-1.5 w-1.5 rounded-full bg-green-500"></span>
								Configured
							</span>
						{:else}
							<span class="flex items-center gap-1.5 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
								Needed for private repos
							</span>
						{/if}
					</div>
					<p class="text-xs text-muted-foreground mt-1 mb-2">
						Add a <a href="https://github.com/settings/tokens" target="_blank" rel="noopener noreferrer" class="underline font-medium text-foreground">personal access token</a> to access private repos and repos you contribute to. Needs <code class="text-[10px] bg-muted px-1 py-0.5 rounded">repo</code> scope.
					</p>
					<div class="flex gap-2">
						<input
							type="password"
							bind:value={githubToken}
							placeholder="ghp_..."
							class="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
						/>
						<button
							onclick={handleSaveToken}
							disabled={!githubToken.trim() || githubSaving}
							class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
						>
							{githubSaving ? 'Saving...' : 'Save'}
						</button>
					</div>
					{#if hasGithubToken}
						<button
							onclick={handleRemoveToken}
							class="mt-2 text-xs text-destructive hover:underline"
						>
							Remove token
						</button>
					{/if}
				</div>
			{/if}

			{#if githubMessage}
				<p class="text-xs {githubMessage.includes('saved') || githubMessage.includes('removed') ? 'text-green-600 dark:text-green-400' : 'text-destructive'}">
					{githubMessage}
				</p>
			{/if}
		</div>
	</section>

	<!-- Database -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold">Database</h2>
		<div class="space-y-4 rounded-lg border border-border bg-card p-5">
			{#if dbInfo}
				<div class="space-y-3 text-sm">
					<div class="flex justify-between gap-3">
						<span class="text-muted-foreground shrink-0">Path</span>
						<span class="truncate text-right font-mono text-xs" title={dbInfo.db_path}>
							{formatPath(dbInfo.db_path)}
						</span>
					</div>
					<div class="flex justify-between">
						<span class="text-muted-foreground">Size</span>
						<span>{formatBytes(dbInfo.db_size_bytes)}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-muted-foreground">Sessions</span>
						<span>{dbInfo.session_count}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-muted-foreground">Observations</span>
						<span>{dbInfo.observation_count.toLocaleString()}</span>
					</div>
					<div class="flex justify-between">
						<span class="text-muted-foreground">Text entries</span>
						<span>{dbInfo.text_entry_count.toLocaleString()}</span>
					</div>
				</div>
			{:else}
				<p class="text-sm text-muted-foreground">Could not connect to backend</p>
			{/if}

			<div class="border-t border-border pt-4">
				<h3 class="text-sm font-medium">Link an existing database</h3>
				<p class="mt-1 text-xs text-muted-foreground">
					Point log(ger) at a different <code class="rounded bg-muted px-1 py-0.5 text-[10px]">.db</code> file.
					The current database will be backed up automatically before being replaced. To import
					from CSV instead, use the <a href="/data" class="text-primary hover:underline">Data page</a>.
				</p>

				<div class="mt-3 flex flex-wrap items-center gap-2">
					<button
						onclick={pickReplaceFile}
						disabled={dbReplacing}
						class="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-sm font-medium transition-colors hover:border-primary hover:text-primary disabled:opacity-50"
					>
						<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"/>
						</svg>
						Choose .db file…
					</button>

					<button
						onclick={handleDownloadDB}
						class="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
						title="Download current database"
					>
						<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"/>
						</svg>
						Download current
					</button>

					<input
						bind:this={dbReplaceInput}
						type="file"
						accept=".db,.sqlite,application/vnd.sqlite3"
						class="hidden"
						onchange={onReplaceFileChosen}
					/>
				</div>

				{#if pendingReplaceFile}
					<div class="mt-3 rounded-md border border-amber-300/50 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-700/30 p-3">
						<p class="text-sm font-medium">Replace database?</p>
						<p class="mt-0.5 text-xs text-muted-foreground">
							Selected: <span class="font-mono">{pendingReplaceFile.name}</span>
							({(pendingReplaceFile.size / 1024 / 1024).toFixed(2)} MB)
						</p>
						<p class="mt-1.5 text-xs text-muted-foreground">
							The current database will be saved as a timestamped backup next to it.
							Existing in-flight requests may briefly fail during the swap.
						</p>
						<div class="mt-3 flex gap-2">
							<button
								onclick={confirmReplaceDB}
								disabled={dbReplacing}
								class="rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-amber-700 disabled:opacity-50"
							>
								{dbReplacing ? 'Replacing…' : 'Replace database'}
							</button>
							<button
								onclick={cancelReplace}
								disabled={dbReplacing}
								class="rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
							>
								Cancel
							</button>
						</div>
					</div>
				{/if}

				{#if dbMessage}
					<p class="mt-2 text-xs {dbMessageIsError ? 'text-destructive' : 'text-green-600 dark:text-green-400'}">
						{dbMessage}
					</p>
				{/if}
			</div>
		</div>
	</section>
</div>
