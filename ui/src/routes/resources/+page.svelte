<script>
	import { api } from '$lib/api/client';

	let resources = $state([]);
	let error = $state('');
	let showDialog = $state(false);
	let editingId = $state(null);
	let loaded = $state(false);

	// Form state
	let form = $state({
		name: '',
		resource_type: 'secret',
		access_level: 'red',
		value: '',
		description: '',
		// MCP tool fields
		mcp_command: '',
		mcp_args: '',
		mcp_env: '',
		mcp_tool_name: ''
	});

	const levelColors = { red: 'var(--color-red)', yellow: 'var(--color-yellow)', green: 'var(--color-green)' };

	async function loadResources() {
		try {
			resources = await api.listResources();
		} catch (e) {
			error = e.message;
		}
	}

	$effect(() => { if (!loaded) { loaded = true; loadResources(); } });

	function openCreate() {
		editingId = null;
		form = { name: '', resource_type: 'secret', access_level: 'red', value: '', description: '', mcp_command: '', mcp_args: '', mcp_env: '', mcp_tool_name: '' };
		showDialog = true;
	}

	function openEdit(r) {
		editingId = r.id;
		form = { name: r.name, resource_type: r.resource_type, access_level: r.access_level, value: '', description: r.description || '', mcp_command: '', mcp_args: '', mcp_env: '', mcp_tool_name: '' };
		showDialog = true;
	}

	async function saveResource() {
		if (!editingId && !form.name.trim()) {
			error = 'Name is required';
			return;
		}
		try {
			if (editingId) {
				await api.updateResource(editingId, {
					access_level: form.access_level,
					description: form.description || null
				});
			} else {
				const payload = {
					name: form.name,
					resource_type: form.resource_type,
					access_level: form.access_level,
					description: form.description || null
				};
				if (form.resource_type === 'mcp_tool') {
					const serverConfig = { command: form.mcp_command };
					if (form.mcp_args.trim()) {
						serverConfig.args = form.mcp_args.trim().split(/\s+/).filter(Boolean);
					}
					if (form.mcp_env.trim()) {
						const envObj = {};
						for (const line of form.mcp_env.split('\n')) {
							const eq = line.indexOf('=');
							if (eq > 0) envObj[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
						}
						serverConfig.env = envObj;
					}
					payload.mcp_server_url = JSON.stringify(serverConfig);
					payload.mcp_tool_name = form.mcp_tool_name || form.name;
				} else {
					payload.value = form.value || null;
				}
				await api.createResource(payload);
			}
			showDialog = false;
			await loadResources();
		} catch (e) {
			error = e.message;
		}
	}

	async function deleteResource(id) {
		if (!confirm('Delete this resource?')) return;
		try {
			await api.deleteResource(id);
			await loadResources();
		} catch (e) {
			error = e.message;
		}
	}
</script>

<div class="max-w-5xl">
	<div class="flex items-center justify-between mb-6">
		<h2 class="text-2xl font-bold">Resources</h2>
		<button
			onclick={openCreate}
			class="px-4 py-2 bg-white text-black rounded-md text-sm font-medium hover:bg-gray-200 transition-colors"
		>
			+ Add Resource
		</button>
	</div>

	{#if error}
		<div class="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-400 mb-4">
			{error}
			<button onclick={() => error = ''} class="ml-2 underline">dismiss</button>
		</div>
	{/if}

	<!-- Resources table -->
	<div class="rounded-lg border border-[var(--color-border)] overflow-hidden">
		<table class="w-full text-sm">
			<thead>
				<tr class="bg-[var(--color-surface)] border-b border-[var(--color-border)]">
					<th class="text-left p-3 font-medium text-[var(--color-text-muted)]">Name</th>
					<th class="text-left p-3 font-medium text-[var(--color-text-muted)]">Type</th>
					<th class="text-left p-3 font-medium text-[var(--color-text-muted)]">Level</th>
					<th class="text-left p-3 font-medium text-[var(--color-text-muted)]">Description</th>
					<th class="text-right p-3 font-medium text-[var(--color-text-muted)]">Accesses</th>
					<th class="text-right p-3 font-medium text-[var(--color-text-muted)]">Actions</th>
				</tr>
			</thead>
			<tbody>
				{#each resources as r (r.id)}
					<tr class="border-b border-[var(--color-border)] hover:bg-[var(--color-surface)] transition-colors">
						<td class="p-3 font-mono font-medium">{r.name}</td>
						<td class="p-3 text-[var(--color-text-muted)]">{r.resource_type}</td>
						<td class="p-3">
							<span class="inline-flex items-center gap-1.5">
								<span
									class="w-2.5 h-2.5 rounded-full"
									style="background-color: {levelColors[r.access_level]}"
								></span>
								{r.access_level}
							</span>
						</td>
						<td class="p-3 text-[var(--color-text-muted)] max-w-xs truncate">{r.description || ''}</td>
						<td class="p-3 text-right tabular-nums">{r.access_count}</td>
						<td class="p-3 text-right">
							<button onclick={() => openEdit(r)} class="text-[var(--color-text-muted)] hover:text-white mr-2">edit</button>
							<button onclick={() => deleteResource(r.id)} class="text-red-400 hover:text-red-300">delete</button>
						</td>
					</tr>
				{:else}
					<tr>
						<td colspan="6" class="p-8 text-center text-[var(--color-text-muted)]">
							No resources yet. Click "Add Resource" to get started.
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

<!-- Dialog -->
{#if showDialog}
	<div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onclick={() => showDialog = false}>
		<div class="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-6 w-full max-w-md" onclick={(e) => e.stopPropagation()}>
			<h3 class="text-lg font-bold mb-4">{editingId ? 'Edit Resource' : 'Add Resource'}</h3>

			<div class="flex flex-col gap-3">
				{#if !editingId}
					<label class="flex flex-col gap-1">
						<span class="text-sm text-[var(--color-text-muted)]">Name</span>
						<input bind:value={form.name} class="bg-[var(--color-bg)] border border-[var(--color-border)] rounded px-3 py-2 text-sm" placeholder="OPENAI_API_KEY" />
					</label>
					<label class="flex flex-col gap-1">
						<span class="text-sm text-[var(--color-text-muted)]">Type</span>
						<select bind:value={form.resource_type} class="bg-[var(--color-bg)] border border-[var(--color-border)] rounded px-3 py-2 text-sm">
							<option value="secret">Secret</option>
							<option value="file">File</option>
							<option value="mcp_tool">MCP Tool</option>
						</select>
					</label>
					{#if form.resource_type === 'secret'}
						<label class="flex flex-col gap-1">
							<span class="text-sm text-[var(--color-text-muted)]">Value</span>
							<input bind:value={form.value} type="password" class="bg-[var(--color-bg)] border border-[var(--color-border)] rounded px-3 py-2 text-sm font-mono" placeholder="sk-..." />
						</label>
					{:else if form.resource_type === 'mcp_tool'}
						<label class="flex flex-col gap-1">
							<span class="text-sm text-[var(--color-text-muted)]">Command</span>
							<input bind:value={form.mcp_command} class="bg-[var(--color-bg)] border border-[var(--color-border)] rounded px-3 py-2 text-sm font-mono" placeholder="npx" />
						</label>
						<label class="flex flex-col gap-1">
							<span class="text-sm text-[var(--color-text-muted)]">Arguments (space-separated)</span>
							<input bind:value={form.mcp_args} class="bg-[var(--color-bg)] border border-[var(--color-border)] rounded px-3 py-2 text-sm font-mono" placeholder="-y @example/mcp-server" />
						</label>
						<label class="flex flex-col gap-1">
							<span class="text-sm text-[var(--color-text-muted)]">Environment Variables (KEY=VALUE, one per line)</span>
							<textarea bind:value={form.mcp_env} rows="2" class="bg-[var(--color-bg)] border border-[var(--color-border)] rounded px-3 py-2 text-sm font-mono" placeholder="API_KEY=abc123"></textarea>
						</label>
						<label class="flex flex-col gap-1">
							<span class="text-sm text-[var(--color-text-muted)]">Downstream Tool Name</span>
							<input bind:value={form.mcp_tool_name} class="bg-[var(--color-bg)] border border-[var(--color-border)] rounded px-3 py-2 text-sm font-mono" placeholder="Defaults to resource name" />
						</label>
					{/if}
				{/if}

				<label class="flex flex-col gap-1">
					<span class="text-sm text-[var(--color-text-muted)]">Access Level</span>
					<div class="flex gap-2">
						{#each ['red', 'yellow', 'green'] as level}
							<button
								onclick={() => form.access_level = level}
								class="flex-1 py-2 rounded text-sm font-medium border transition-colors"
								class:border-white={form.access_level === level}
								class:border-transparent={form.access_level !== level}
								style="background-color: color-mix(in srgb, {levelColors[level]} 20%, transparent)"
							>
								{level}
							</button>
						{/each}
					</div>
				</label>

				<label class="flex flex-col gap-1">
					<span class="text-sm text-[var(--color-text-muted)]">Description</span>
					<input bind:value={form.description} class="bg-[var(--color-bg)] border border-[var(--color-border)] rounded px-3 py-2 text-sm" placeholder="Optional description" />
				</label>
			</div>

			<div class="flex justify-end gap-2 mt-6">
				<button onclick={() => showDialog = false} class="px-4 py-2 text-sm text-[var(--color-text-muted)] hover:text-white">Cancel</button>
				<button onclick={saveResource} class="px-4 py-2 bg-white text-black rounded-md text-sm font-medium hover:bg-gray-200">
					{editingId ? 'Save' : 'Create'}
				</button>
			</div>
		</div>
	</div>
{/if}
