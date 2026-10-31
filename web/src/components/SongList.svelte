<script lang="ts">
	import { app } from '../lib/state.svelte.js';
	import { ui } from '../lib/ui.svelte.js';
	import { AudioLines, Library, Sparkles } from '@lucide/svelte';
	import SongCard from './SongCard.svelte';
	import productMascot from '../assets/yue2_mascot.webp';
	let { library = false }: { library?: boolean } = $props();
	let query = $state('');
	let favorites = $state(false);
	let songs = $derived(
		app.songs.filter(
			(song) =>
				(!favorites || song.favorite) &&
				`${song.name} ${song.style}`.toLowerCase().includes(query.toLowerCase())
		)
	);
</script>

<div class="library-heading">
	<h2 class="section-heading">
		{#if library}<Library size={18} /> Song library{:else}<AudioLines size={18} /> Your songs{/if}<span
			>{app.songs.length}</span
		>
	</h2>
	<span class="storage-note">Saved in this browser</span>
</div>
{#if library && app.songs.length}
	<div class="library-tools">
		<input
			type="search"
			aria-label="Search songs"
			placeholder="Search songs…"
			bind:value={query}
		/><label><input type="checkbox" bind:checked={favorites} /> Favorites only</label>
	</div>
{/if}
<div class="song-list">
	{#each library ? songs : app.songs as song (song.id)}
		<SongCard {song} />
	{:else}
		<div class="empty-library">
			{#if app.songs.length}
				<AudioLines size={30} />
			{:else}
				<img class="empty-mascot" src={productMascot} alt="" width="140" height="140" />
			{/if}
			<h3>{app.songs.length ? 'No matching songs' : 'A little quiet in here'}</h3>
			<p>
				{app.songs.length
					? 'Try another search or turn off the favorites filter.'
					: 'Your generated and imported songs will appear here. Play, download and return to any take.'}
			</p>
			{#if !app.songs.length}<button
					type="button"
					class="secondary-button"
					onclick={() => (ui.examplesOpen = true)}><Sparkles size={15} /> Explore examples</button
				>{/if}
		</div>
	{/each}
</div>

<style>
	.empty-mascot {
		width: 140px;
		height: auto;
		margin-bottom: 8px;
	}
	.song-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		overflow-y: auto;
	}
	.library-heading {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
		padding: 20px 0 16px;
		border-top: 1px solid var(--line-soft);
	}
	h2 span {
		padding: 2px 6px;
		border-radius: 4px;
		background: var(--bg-btn);
		font-size: 0.65rem;
		color: var(--fg-dim);
	}
	.storage-note {
		color: var(--fg-dim);
		font-size: 0.68rem;
	}
	.empty-library {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 12px;
		padding: 32px 20px;
		border: 1px dashed var(--border);
		border-radius: 7px;
		text-align: center;
		background: var(--bg-input);
	}
	.empty-library > :global(svg) {
		color: var(--accent);
		opacity: 0.75;
	}
	h3 {
		font-size: 0.88rem;
		margin: 0;
	}
	p {
		max-width: 380px;
		margin: 0;
		font-size: 0.75rem;
		color: var(--fg-dim);
		line-height: 1.6;
	}
	.library-tools {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 16px;
		margin-bottom: 18px;
	}
	.library-tools input[type='search'] {
		flex: 1;
		min-width: 170px;
	}
	.library-tools label {
		display: flex;
		align-items: center;
		gap: 7px;
		font-size: 0.74rem;
		color: var(--fg-dim);
	}
</style>
