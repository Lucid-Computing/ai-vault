<script>
	import { api } from '$lib/api/client';

	let approvals = $state([]);
	let error = $state('');
	let filter = $state('pending');

	async function loadApprovals() {
		try {
			approvals = await api.listApprovals(filter || undefined);
		} catch (e) {
			error = e.message;
		}
	}

	$effect(() => { filter; loadApprovals(); });

	async function approve(id) {
		try {
			await api.approveRequest(id);
			await loadApprovals();
		} catch (e) {
			error = e.message;
		}
	}

	async function deny(id) {
		try {
			await api.denyRequest(id);
			await loadApprovals();
		} catch (e) {
			error = e.message;
		}
	}

	function formatTime(ts) {
		if (!ts) return '';
		return new Date(ts).toLocaleString();
	}

	const statusColors = {
		pending: 'text-yellow-400 bg-yellow-500/20',
		approved: 'text-green-400 bg-green-500/20',
		denied: 'text-red-400 bg-red-500/20',
		expired: 'text-gray-400 bg-gray-500/20'
	};
</script>

<div class="max-w-4xl">
	<div class="flex items-center justify-between mb-6">
		<h2 class="text-2xl font-bold">Approvals</h2>
		<div class="flex gap-1 bg-[var(--color-surface)] rounded-md p-1">
			{#each ['pending', 'approved', 'denied', ''] as f}
				<button
					onclick={() => { filter = f; loadApprovals(); }}
					class="px-3 py-1 rounded text-sm transition-colors"
					class:bg-white={filter === f}
					class:text-black={filter === f}
					class:text-[var(--color-text-muted)]={filter !== f}
				>
					{f || 'all'}
				</button>
			{/each}
		</div>
	</div>

	{#if error}
		<div class="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-400 mb-4">{error}</div>
	{/if}

	<div class="flex flex-col gap-3">
		{#each approvals as a (a.id)}
			<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
				<div class="flex items-start justify-between">
					<div>
						<p class="font-mono font-medium">{a.resource_name}</p>
						{#if a.purpose}
							<p class="text-sm text-[var(--color-text-muted)] mt-1">"{a.purpose}"</p>
						{/if}
						{#if a.caller}
							<p class="text-xs text-[var(--color-text-muted)] mt-1">from: {a.caller}</p>
						{/if}
						<p class="text-xs text-[var(--color-text-muted)] mt-2">{formatTime(a.requested_at)}</p>
					</div>

					<div class="flex items-center gap-2">
						<span class="px-2 py-0.5 rounded text-xs font-medium {statusColors[a.status]}">
							{a.status}
						</span>

						{#if a.status === 'pending'}
							<button
								onclick={() => approve(a.id)}
								class="px-3 py-1.5 bg-green-600 hover:bg-green-500 text-white rounded text-sm font-medium transition-colors"
							>
								Approve
							</button>
							<button
								onclick={() => deny(a.id)}
								class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded text-sm font-medium transition-colors"
							>
								Deny
							</button>
						{/if}
					</div>
				</div>

				{#if a.decision_reason}
					<p class="text-sm text-[var(--color-text-muted)] mt-2 border-t border-[var(--color-border)] pt-2">
						Reason: {a.decision_reason}
					</p>
				{/if}
			</div>
		{:else}
			<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center text-[var(--color-text-muted)]">
				No {filter || ''} approvals.
			</div>
		{/each}
	</div>
</div>
