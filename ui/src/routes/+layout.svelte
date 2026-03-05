<script>
	import '../app.css';

	let { children } = $props();

	const nav = [
		{ href: '/', label: 'Dashboard', icon: '◉' },
		{ href: '/resources', label: 'Resources', icon: '◈' },
		{ href: '/activity', label: 'Activity', icon: '◷' },
		{ href: '/approvals', label: 'Approvals', icon: '◎' }
	];
</script>

<div class="flex min-h-screen">
	<!-- Sidebar -->
	<nav class="w-56 border-r border-[var(--color-border)] p-4 flex flex-col gap-1">
		<div class="mb-6 px-2">
			<h1 class="text-lg font-bold tracking-tight">AI Vault</h1>
			<p class="text-xs text-[var(--color-text-muted)]">Resource Access Control</p>
		</div>

		{#each nav as item}
			<a
				href={item.href}
				class="flex items-center gap-2 px-3 py-2 rounded-md text-sm hover:bg-[var(--color-surface)] transition-colors"
			>
				<span class="text-base">{item.icon}</span>
				{item.label}
			</a>
		{/each}

		<div class="mt-auto pt-4 border-t border-[var(--color-border)]">
			<p class="px-2 text-xs text-[var(--color-text-muted)]">v0.1.0 — localhost:8484</p>
		</div>
	</nav>

	<!-- Main content -->
	<main class="flex-1 p-6 overflow-auto">
		{@render children()}
	</main>
</div>
