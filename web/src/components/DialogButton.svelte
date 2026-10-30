<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		onclick,
		children
	}: {
		onclick: (e: MouseEvent) => void;
		children: Snippet;
	} = $props();
</script>

<button type="button" {onclick}>{@render children()}</button>

<style>
	button {
		background: var(--bg-btn);
		border: 1px solid var(--border);
		cursor: pointer;
		padding: 8px 13px;
		min-height: 36px;
		color: var(--fg);
		font-size: 0.8rem;
		border-radius: 3px;
	}
	button:hover {
		background: var(--bg-btn-hover);
	}
</style>
