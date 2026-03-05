<script>
	import { api } from '$lib/api/client';

	let logs = $state([]);
	let error = $state('');
	let loaded = $state(false);

	$effect(() => {
		if (loaded) return;
		loaded = true;
		api.listActivity(100).then(data => logs = data).catch(e => error = e.message);
	});

	function formatTime(ts) {
		if (!ts) return '';
		return new Date(ts).toLocaleString();
	}
</script>

<div class="max-w-5xl">
	<h2 class="text-2xl font-bold mb-6">Activity Log</h2>

	{#if error}
		<div class="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-400 mb-4">{error}</div>
	{/if}

	<div class="rounded-lg border border-[var(--color-border)] overflow-hidden">
		<table class="w-full text-sm">
			<thead>
				<tr class="bg-[var(--color-surface)] border-b border-[var(--color-border)]">
					<th class="text-left p-3 font-medium text-[var(--color-text-muted)]">Time</th>
					<th class="text-left p-3 font-medium text-[var(--color-text-muted)]">Action</th>
					<th class="text-left p-3 font-medium text-[var(--color-text-muted)]">Resource</th>
					<th class="text-left p-3 font-medium text-[var(--color-text-muted)]">Caller</th>
					<th class="text-left p-3 font-medium text-[var(--color-text-muted)]">Status</th>
				</tr>
			</thead>
			<tbody>
				{#each logs as log (log.id)}
					<tr class="border-b border-[var(--color-border)]">
						<td class="p-3 text-[var(--color-text-muted)] whitespace-nowrap">{formatTime(log.timestamp)}</td>
						<td class="p-3">
							<span class="px-2 py-0.5 rounded text-xs font-medium {log.success ? 'text-green-400 bg-green-900' : 'text-red-400 bg-red-900'}">
								{log.action}
							</span>
						</td>
						<td class="p-3 font-mono">{log.resource_name}</td>
						<td class="p-3 text-[var(--color-text-muted)]">{log.caller || '-'}</td>
						<td class="p-3">{log.success ? 'OK' : 'DENIED'}</td>
					</tr>
				{:else}
					<tr>
						<td colspan="5" class="p-8 text-center text-[var(--color-text-muted)]">No activity yet.</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
