<script lang="ts">
	import { msg } from '../lib/i18n.svelte.js';
	import { language } from '../lib/i18n.svelte.js';
	let {
		label,
		unit,
		points,
		maximum,
		windowSeconds,
		now
	}: {
		label: string;
		unit: string;
		points: { timestamp: number; value: number }[];
		maximum?: number | null;
		windowSeconds: number;
		now: number;
	} = $props();
	let hover = $state<number | null>(null);
	let samples = $derived(
		points.filter((p) => Number.isFinite(p.value) && p.timestamp >= now - windowSeconds * 1000)
	);
	let current = $derived(samples.at(-1)?.value ?? 0);
	let peak = $derived(samples.length ? Math.max(...samples.map((p) => p.value)) : 0);
	let average = $derived(
		samples.length ? samples.reduce((sum, p) => sum + p.value, 0) / samples.length : 0
	);
	let ceiling = $derived(Math.max(maximum || peak * 1.15, 1));
	const fmt = (value: number) => value.toLocaleString(language.code, { maximumFractionDigits: 1 });
	const x = (timestamp: number) =>
		Math.max(
			0,
			Math.min(400, (400 * (timestamp - (now - windowSeconds * 1000))) / (windowSeconds * 1000))
		);
	const y = (value: number) => 74 - Math.max(0, Math.min(1, value / ceiling)) * 66;
	let line = $derived(samples.map((p) => `${x(p.timestamp)},${y(p.value)}`).join(' '));
	let selected = $derived(
		hover == null || !samples.length
			? null
			: samples.reduce((a, b) =>
					Math.abs(x(a.timestamp) - hover!) < Math.abs(x(b.timestamp) - hover!) ? a : b
				)
	);
	function move(event: PointerEvent) {
		const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
		hover = ((event.clientX - rect.left) / rect.width) * 400;
	}
</script>

<div
	class="metric-chart"
	role="group"
	aria-label={msg('{label} chart', { label: msg(label) })}
	onpointermove={move}
	onpointerleave={() => (hover = null)}
>
	<div class="metric-heading">
		<span>{msg(label)}</span><strong>{fmt(current)}<small>{unit}</small></strong>
	</div>
	<svg
		viewBox="0 0 400 82"
		preserveAspectRatio="none"
		role="img"
		aria-label={msg(
			'{label}: {value} {unit}, average {average}, peak {peak} over {seconds} seconds',
			{
				label: msg(label),
				value: fmt(current),
				unit,
				average: fmt(average),
				peak: fmt(peak),
				seconds: windowSeconds
			}
		)}
	>
		<title>{msg(label)} {msg('history')}</title><path d="M0 8H400M0 41H400M0 74H400" class="grid" />
		{#if samples.length}<polygon
				points={`${x(samples[0].timestamp)},74 ${line} ${x(samples.at(-1)!.timestamp)},74`}
				class="area"
			/><polyline points={line} class="line" /><circle
				cx={x(samples.at(-1)!.timestamp)}
				cy={y(current)}
				r="3"
			/>{/if}
		{#if selected}<path d={`M${x(selected.timestamp)} 3V77`} class="crosshair" /><circle
				cx={x(selected.timestamp)}
				cy={y(selected.value)}
				r="4"
			/>{/if}
	</svg>
	<div class="metric-footer">
		{#if selected}<span
				>{new Date(selected.timestamp).toLocaleTimeString(language.code)} · {fmt(selected.value)}
				{unit}</span
			>{:else}<span>{msg('Avg')} {fmt(average)} {unit}</span><span
				>{msg('Peak')} {fmt(peak)} {unit}</span
			>{/if}
	</div>
</div>

<style>
	.metric-chart {
		min-width: 0;
		padding: 13px;
		border: 1px solid var(--line-soft);
		border-radius: 6px;
		background: var(--bg-input);
	}
	.metric-heading {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
		font-size: 0.7rem;
		color: var(--fg-dim);
	}
	strong {
		font-size: 0.85rem;
		color: var(--fg);
		font-variant-numeric: tabular-nums;
	}
	small {
		margin-left: 4px;
		font-size: 0.65rem;
		font-weight: 500;
		color: var(--fg-dim);
	}
	svg {
		display: block;
		width: 100%;
		height: 82px;
		margin: 10px 0 5px;
		overflow: visible;
	}
	.grid {
		stroke: var(--border);
		opacity: 0.5;
		stroke-dasharray: 3 5;
		stroke-width: 0.6;
	}
	.line {
		fill: none;
		stroke: var(--accent);
		stroke-width: 1.8;
		vector-effect: non-scaling-stroke;
	}
	.area {
		fill: var(--accent);
		opacity: 0.09;
	}
	circle {
		fill: var(--accent-hover);
	}
	.crosshair {
		stroke: var(--fg-dim);
		stroke-width: 0.7;
		stroke-dasharray: 3 3;
	}
	.metric-footer {
		display: flex;
		justify-content: space-between;
		gap: 6px;
		color: var(--fg-dim);
		font-size: 0.61rem;
		min-height: 14px;
	}
</style>
