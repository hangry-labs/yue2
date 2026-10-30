<script lang="ts">
	import { Settings2, Boxes, ShieldCheck, Volume2, Check, Minus } from '@lucide/svelte';
	import { app } from '../lib/state.svelte.js';
	import GpuMonitor from './GpuMonitor.svelte';
	import LogCard from './LogCard.svelte';
	let { active }: { active: boolean } = $props();
	const filename = (path?: string) => path?.split(/[/\\]/).pop() || 'Unavailable';
</script>

<div class="system-view">
	<div class="page-heading">
		<h2 class="section-heading"><Settings2 size={20} /> System</h2>
		<p>Local runtime, models and browser preferences.</p>
	</div>
	<div class="system-grid">
		<div class="system-controls">
			<section class="surface">
				<h3 class="section-heading"><Boxes size={17} /> Runtime and models</h3>
				<div class="service-state" class:connected={!!app.props}>
					{app.props ? 'Service connected' : 'Service unavailable'}
				</div>
				<p class="field-help">
					Models load on demand for each generation stage. A connected service does not mean the
					weights are resident in VRAM.
				</p>
				<dl>
					<dt>Song model</dt>
					<dd>{filename(app.props?.model)}</dd>
					<dt>Audio VAE</dt>
					<dd>{filename(app.props?.vae)}</dd>
					<dt>Audio output</dt>
					<dd>{app.props ? `${app.props.sample_rate / 1000} kHz stereo` : 'Unavailable'}</dd>
					<dt>Version</dt>
					<dd>{app.props?.version || __YUE2_VERSION__}</dd>
				</dl>
				<p class="field-help">
					Model choice and GPU allocation are configured when the container starts. Weights are
					mounted read-only from your machine.
				</p>
			</section>
			<section class="surface">
				<h3>Available tools</h3>
				<ul class="capabilities">
					<li><Check size={15} /> Song generation and VAE</li>
					<li class:unavailable={!app.props?.capabilities?.transcribe}>
						{#if app.props?.capabilities?.transcribe}<Check size={15} />{:else}<Minus
								size={15}
							/>{/if} Score transcription
						<span
							>{app.props?.capabilities?.transcribe
								? 'Enabled'
								: 'Additional models required'}</span
						>
					</li>
					<li class:unavailable={!app.props?.capabilities?.tokenize}>
						{#if app.props?.capabilities?.tokenize}<Check size={15} />{:else}<Minus
								size={15}
							/>{/if} Audio tokenization
						<span
							>{app.props?.capabilities?.tokenize ? 'Enabled' : 'Additional models required'}</span
						>
					</li>
				</ul>
			</section>
			<section class="surface">
				<h3>Browser preferences</h3>
				<label class="preference-row"
					><span><Volume2 size={15} /> Playback volume</span><input
						type="range"
						aria-label="Playback volume"
						min="0"
						max="1"
						step="0.01"
						bind:value={app.volume}
					/></label
				>
				<p class="field-help">These preferences are saved in this browser.</p>
			</section>
			<section class="surface">
				<h3 class="section-heading"><ShieldCheck size={17} /> Your machine, your music</h3>
				<p class="field-help">
					Generation runs locally. Songs and prompts already saved by the studio remain in this
					browser. Download the songs you want to keep. Model licenses apply separately from the
					application.
				</p>
			</section>
		</div>
		<div class="system-telemetry">
			<GpuMonitor {active} />{#if active}<LogCard />{/if}
		</div>
	</div>
</div>

<style>
	.system-view {
		padding: 30px;
		max-width: 1600px;
		margin: 0 auto;
	}
	.page-heading {
		margin-bottom: 24px;
	}
	.page-heading p {
		color: var(--fg-dim);
		font-size: 0.78rem;
	}
	.system-grid {
		display: grid;
		grid-template-columns: minmax(300px, 0.8fr) minmax(420px, 1.2fr);
		align-items: start;
		gap: 22px;
	}
	.system-controls,
	.system-telemetry {
		min-width: 0;
	}
	dl {
		display: grid;
		grid-template-columns: 100px minmax(0, 1fr);
		gap: 15px 12px;
		margin: 22px 0;
	}
	dt {
		color: var(--fg-dim);
		font-size: 0.72rem;
	}
	dd {
		margin: 0;
		font-size: 0.73rem;
		overflow-wrap: anywhere;
	}
	.service-state {
		padding: 10px;
		margin-top: 19px;
		border-left: 3px solid var(--error);
		background: var(--bg-input);
		font-size: 0.74rem;
	}
	.service-state.connected {
		border-color: var(--ok);
	}
	.capabilities {
		list-style: none;
		margin: 20px 0 0;
		padding: 0;
		display: grid;
		gap: 15px;
	}
	.capabilities li {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 7px;
		font-size: 0.74rem;
	}
	.capabilities :global(svg) {
		color: var(--ok);
	}
	.capabilities li.unavailable :global(svg) {
		color: var(--fg-dim);
	}
	.capabilities span {
		flex-basis: 100%;
		margin-left: 22px;
		font-size: 0.65rem;
		color: var(--fg-dim);
	}
	.preference-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		margin-top: 19px;
		font-size: 0.74rem;
	}
	.preference-row > span {
		display: flex;
		align-items: center;
		gap: 7px;
	}
	.preference-row input {
		width: 110px;
	}
	.system-telemetry > :global(.card) {
		margin-top: 20px;
	}
	@media (max-width: 1000px) {
		.system-grid {
			grid-template-columns: 1fr;
		}
	}
	@media (max-width: 540px) {
		.system-view {
			padding: 22px 16px;
		}
	}
</style>
