<script>
	import { api } from '$lib/api/client';

	let overview = $state(null);
	let error = $state('');
	let loaded = $state(false);

	const levelColors = { red: 'var(--color-red)', yellow: 'var(--color-yellow)', green: 'var(--color-green)' };

	async function load() {
		if (loaded) return;
		loaded = true;
		try {
			overview = await api.getOverview();
		} catch (e) {
			error = e.message;
		}
	}

	async function refresh() {
		try {
			overview = await api.getOverview();
		} catch (e) {
			error = e.message;
		}
	}

	async function handleApproval(id, action) {
		try {
			if (action === 'approve') {
				await api.approveRequest(id);
			} else {
				await api.denyRequest(id);
			}
			await refresh();
		} catch (e) {
			error = e.message;
		}
	}

	function timeAgo(ts) {
		if (!ts) return '';
		const now = Date.now();
		const then = new Date(ts).getTime();
		const diff = Math.floor((now - then) / 1000);
		if (diff < 60) return `${diff}s ago`;
		if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
		if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
		return `${Math.floor(diff / 86400)}d ago`;
	}

	function actionLabel(action) {
		const labels = {
			'access_granted': 'accessed',
			'access_denied': 'denied',
			'approval_granted': 'approved',
			'approval_denied': 'denied',
			'tool_called': 'called',
			'declare_access': 'declared',
		};
		return labels[action] || action;
	}

	$effect(() => { load(); });
</script>

<div class="max-w-5xl">
	<div class="flex items-center justify-between mb-6">
		<div class="flex items-center gap-4">
			<h2 class="text-2xl font-bold">Dashboard</h2>
			{#if overview}
				<div class="flex items-center gap-3 text-sm text-[var(--color-text-muted)]">
					{#each [['red', 'Blocked'], ['yellow', 'Ask'], ['green', 'Open']] as [level, label]}
						{@const count = overview.resources_by_level?.[level] || 0}
						<span class="flex items-center gap-1.5">
							<span class="w-2 h-2 rounded-full" style="background-color: var(--color-{level})"></span>
							{label} <span class="font-medium text-white">{count}</span>
						</span>
					{/each}
				</div>
			{/if}
		</div>
		<a href="/resources" class="px-4 py-2 bg-white text-black rounded-md text-sm font-medium hover:bg-gray-200 transition-colors">
			+ Add Resource
		</a>
	</div>

	{#if error}
		<div class="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-400 mb-4">
			{error}
			<button onclick={() => error = ''} class="ml-2 underline">dismiss</button>
		</div>
	{/if}

	{#if overview}

		<!-- Two-column layout -->
		<div class="grid grid-cols-2 gap-6 mb-6">
			<!-- Pending Approvals -->
			<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
				<div class="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
					<h3 class="font-semibold">Pending Approvals</h3>
					{#if overview.pending_approvals > 0}
						<span class="text-xs px-2 py-0.5 rounded-full bg-yellow-400/20 text-yellow-400 font-medium">
							{overview.pending_approvals}
						</span>
					{/if}
				</div>
				<div class="p-4">
					{#if overview.pending_approval_list?.length > 0}
						<div class="flex flex-col gap-3">
							{#each overview.pending_approval_list as approval}
								<div class="flex items-center justify-between gap-2">
									<div class="min-w-0 flex-1">
										<p class="font-mono text-sm truncate">{approval.resource_name}</p>
										<p class="text-xs text-[var(--color-text-muted)] truncate">
											{approval.purpose || 'No purpose given'} · {timeAgo(approval.requested_at)}
										</p>
									</div>
									<div class="flex gap-1.5 flex-shrink-0">
										<button
											onclick={() => handleApproval(approval.id, 'approve')}
											class="px-2.5 py-1 text-xs font-medium rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors"
										>
											Allow
										</button>
										<button
											onclick={() => handleApproval(approval.id, 'deny')}
											class="px-2.5 py-1 text-xs font-medium rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
										>
											Deny
										</button>
									</div>
								</div>
							{/each}
						</div>
						{#if overview.pending_approvals > 5}
							<a href="/approvals" class="block mt-3 text-xs text-[var(--color-text-muted)] hover:text-white transition-colors">
								View all {overview.pending_approvals} approvals →
							</a>
						{/if}
					{:else}
						<p class="text-sm text-[var(--color-text-muted)]">No pending approvals</p>
					{/if}
				</div>
			</div>

			<!-- Top Resources -->
			<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
				<div class="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
					<h3 class="font-semibold">Most Accessed</h3>
					<span class="text-xs text-[var(--color-text-muted)]">{overview.total_accesses} total</span>
				</div>
				<div class="p-4">
					{#if overview.top_resources?.length > 0}
						<div class="flex flex-col gap-2">
							{#each overview.top_resources as resource}
								<div class="flex items-center gap-2">
									<span
										class="w-2 h-2 rounded-full flex-shrink-0"
										style="background-color: {levelColors[resource.access_level]}"
									></span>
									<span class="font-mono text-sm truncate flex-1">{resource.name}</span>
									<span class="text-xs text-[var(--color-text-muted)] flex-shrink-0 tabular-nums">
										{resource.access_count} {resource.access_count === 1 ? 'use' : 'uses'}
									</span>
								</div>
							{/each}
						</div>
						<a href="/resources" class="block mt-3 text-xs text-[var(--color-text-muted)] hover:text-white transition-colors">
							View all {overview.total_resources} resources →
						</a>
					{:else}
						<p class="text-sm text-[var(--color-text-muted)]">No resources accessed yet</p>
					{/if}
				</div>
			</div>
		</div>

		<!-- Recent Activity -->
		<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
			<div class="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
				<h3 class="font-semibold">Recent Activity</h3>
				<span class="text-xs text-[var(--color-text-muted)]">{overview.recent_activity_count} in last 24h</span>
			</div>
			<div class="p-4">
				{#if overview.recent_activities?.length > 0}
					<div class="flex flex-col">
						{#each overview.recent_activities as activity}
							<div class="flex items-center gap-3 py-2 border-b border-[var(--color-border)] last:border-0">
								<span class="w-1.5 h-1.5 rounded-full flex-shrink-0" class:bg-green-400={activity.success} class:bg-red-400={!activity.success}></span>
								<span class="font-mono text-sm truncate flex-1">{activity.resource_name}</span>
								<span class="text-xs px-2 py-0.5 rounded bg-[var(--color-bg)] text-[var(--color-text-muted)] flex-shrink-0">
									{actionLabel(activity.action)}
								</span>
								<span class="text-xs text-[var(--color-text-muted)] flex-shrink-0 w-16 text-right tabular-nums">
									{timeAgo(activity.timestamp)}
								</span>
							</div>
						{/each}
					</div>
					<a href="/activity" class="block mt-3 text-xs text-[var(--color-text-muted)] hover:text-white transition-colors">
						View full activity log →
					</a>
				{:else}
					<p class="text-sm text-[var(--color-text-muted)]">No activity recorded yet</p>
				{/if}
			</div>
		</div>
	{:else}
		<div class="text-[var(--color-text-muted)]">Loading...</div>
	{/if}
</div>
