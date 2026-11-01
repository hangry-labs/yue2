<script lang="ts">
	import { untrack } from 'svelte';
	import { Volume2, VolumeX } from '@lucide/svelte';
	import { app } from '../lib/state.svelte.js';
	import SettingHelp from './SettingHelp.svelte';
	let lastVolume = $state(untrack(() => app.volume || 1));
	const percentage = $derived(Math.round(app.volume * 100));
	$effect(() => {
		if (app.volume > 0) lastVolume = app.volume;
	});
	function toggleMute() {
		app.volume = app.volume > 0 ? 0 : lastVolume;
	}
</script>

<section class="playback-controls" aria-label="Playback controls">
	<div class="playback-heading">
		<label for="playback-volume">Playback volume</label>
		<SettingHelp
			title="Playback volume"
			text="Listening level in this browser. At 100%, a single track plays at its original level. Several tracks playing together share headroom to reduce clipping. Downloads and generation settings are unaffected."
		/>
		<output for="playback-volume">{percentage}%</output>
	</div>
	<div class="playback-level">
		<button
			type="button"
			class="icon-btn"
			aria-label={app.volume === 0 ? 'Unmute playback' : 'Mute playback'}
			aria-pressed={app.volume === 0}
			onclick={toggleMute}
		>
			{#if app.volume === 0}<VolumeX size={17} />{:else}<Volume2 size={17} />{/if}
		</button>
		<input
			id="playback-volume"
			type="range"
			min="0"
			max="1"
			step="0.01"
			aria-label="Playback volume"
			aria-valuetext={`${percentage}%`}
			bind:value={app.volume}
		/>
	</div>
</section>

<style>
	.playback-controls {
		display: grid;
		gap: 9px;
		padding-bottom: 16px;
		border-bottom: 1px solid var(--line-soft);
	}
	.playback-heading,
	.playback-level {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}
	label {
		font-size: 0.75rem;
		font-weight: 650;
	}
	output {
		margin-left: auto;
		font-size: 0.72rem;
		font-variant-numeric: tabular-nums;
		color: var(--fg-dim);
	}
	input {
		flex: 1;
		min-width: 0;
		accent-color: var(--accent);
	}
	button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 30px;
		height: 30px;
		padding: 5px;
		border: 1px solid var(--border);
		border-radius: 6px;
		background: var(--bg-input);
		color: var(--fg-dim);
		cursor: pointer;
	}
	button:hover,
	button[aria-pressed='true'] {
		color: var(--accent);
		border-color: var(--accent);
	}
</style>
