<script lang="ts">
	import { Sparkles, X, ArrowUpRight } from '@lucide/svelte';
	import { ui } from '../lib/ui.svelte.js';
	import { app } from '../lib/state.svelte.js';
	import { examplePrompts, applyExample } from '../lib/example.js';
	import productLogo from '../assets/yue2_logo.webp';
	let dialog: HTMLDialogElement;
	let query = $state('');
	let matches = $derived(
		examplePrompts.filter((ex) =>
			`${ex.title} ${ex.request.style}`.toLowerCase().includes(query.toLowerCase())
		)
	);
	$effect(() => {
		if (ui.examplesOpen && !dialog.open) dialog.showModal();
		else if (!ui.examplesOpen && dialog.open) dialog.close();
	});
	function choose(ex: (typeof examplePrompts)[number]) {
		applyExample(ex);
		ui.view = 'create';
		ui.examplesOpen = false;
	}
</script>

<dialog
	bind:this={dialog}
	onclose={() => (ui.examplesOpen = false)}
	aria-labelledby="examples-heading"
>
	<div class="dialog-heading">
		<h2 id="examples-heading"><Sparkles size={20} /> Find a starting point</h2>
		<button
			type="button"
			class="secondary-button"
			aria-label="Close examples"
			onclick={() => (ui.examplesOpen = false)}><X size={18} /></button
		>
	</div>
	<div class="example-intro">
		<img src={productLogo} alt="" width="110" height="110" />
		<p>
			Choose an upstream example, then make it yours. This replaces the title, style, lyrics and
			score, clears replay inputs, and keeps your generation settings.
		</p>
	</div>
	<label for="example-search">Search examples</label><input
		id="example-search"
		type="search"
		bind:value={query}
		placeholder="Search by title, genre or voice…"
	/>
	<div class="example-grid">
		{#each matches as ex}
			<button
				class="example-card"
				type="button"
				disabled={app.generating}
				onclick={() => choose(ex)}
				><span class="example-title">{ex.title}<ArrowUpRight size={16} /></span><span
					class="example-style">{ex.request.style}</span
				></button
			>
		{:else}<p>No examples match this search.</p>{/each}
	</div>
</dialog>

<style>
	.example-intro {
		display: flex;
		align-items: center;
		gap: 18px;
		margin: 15px 0;
	}
	.example-intro img {
		width: clamp(70px, 15vw, 110px);
		height: auto;
		flex: 0 0 auto;
	}
	dialog {
		width: min(820px, calc(100vw - 30px));
		max-height: 85dvh;
		padding: 24px;
		border: 1px solid var(--border);
		border-radius: 10px;
		color: var(--fg);
		background: var(--bg-card);
	}
	dialog::backdrop {
		background: #000a;
		backdrop-filter: blur(4px);
	}
	.dialog-heading {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 15px;
	}
	h2 {
		display: flex;
		align-items: center;
		gap: 9px;
		margin: 0;
		font-size: 1rem;
	}
	h2 :global(svg) {
		color: var(--accent);
	}
	p {
		color: var(--fg-dim);
		font-size: 0.78rem;
		line-height: 1.65;
	}
	label {
		display: block;
		margin-bottom: 7px;
		font-size: 0.75rem;
	}
	input {
		width: 100%;
	}
	.example-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 10px;
		margin-top: 18px;
	}
	.example-card {
		display: flex;
		flex-direction: column;
		gap: 9px;
		text-align: left;
		padding: 16px;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--bg-input);
	}
	.example-card:hover {
		border-color: var(--accent);
		background: var(--bg-btn);
	}
	.example-title {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
		font-size: 0.8rem;
		font-weight: 650;
	}
	.example-title :global(svg) {
		color: var(--accent);
	}
	.example-style {
		display: -webkit-box;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		-webkit-box-orient: vertical;
		overflow: hidden;
		color: var(--fg-dim);
		font-size: 0.73rem;
		line-height: 1.5;
	}
	@media (max-width: 540px) {
		dialog {
			padding: 18px;
		}
		.example-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
