<script lang="ts">
	import { onMount } from 'svelte';
	import { Activity, Cpu } from '@lucide/svelte';
	import type { GpuSample, GpuSnapshot } from '../lib/gpu.js';
	import GpuChart from './GpuChart.svelte';
	let { active }: { active: boolean } = $props();
	let visible = $state(!document.hidden);
	let gpus = $state<GpuSample[]>([]);
	let history = $state<GpuSample[]>([]);
	let windowSeconds = $state(60);
	let message = $state('Open System to start GPU monitoring.');
	let stale = $state(false);
	let now = $state(Date.now());
	const metrics = [
		{ key: 'gpu_utilization_percent', label: 'GPU utilization', unit: '%', max: 100 },
		{ key: 'memory_used_mb', label: 'VRAM used', unit: 'MiB', maxKey: 'memory_total_mb' },
		{ key: 'temperature_c', label: 'Temperature', unit: '°C', max: 100 },
		{ key: 'power_w', label: 'Power draw', unit: 'W', maxKey: 'power_limit_w' },
		{ key: 'memory_utilization_percent', label: 'Memory controller', unit: '%', max: 100 },
		{ key: 'fan_percent', label: 'Fan speed', unit: '%', max: 100 },
		{ key: 'clock_mhz', label: 'Graphics clock', unit: 'MHz', maxKey: 'clock_max_mhz' },
		{ key: 'memory_clock_mhz', label: 'Memory clock', unit: 'MHz', maxKey: 'memory_clock_max_mhz' }
	] as const;
	onMount(() => {
		try {
			const saved = JSON.parse(sessionStorage.getItem('yue2-gpu-session-v1') || '{}');
			if (Array.isArray(saved.history))
				history = saved.history.filter(
					(s: GpuSample) => s.timestamp >= Date.now() - 600000 && Number.isFinite(s.index)
				);
			windowSeconds = saved.windowSeconds === 600 ? 600 : 60;
		} catch {
			/* An empty history is safe. */
		}
		const update = () => (visible = !document.hidden);
		document.addEventListener('visibilitychange', update);
		return () => document.removeEventListener('visibilitychange', update);
	});
	$effect(() => {
		const value = JSON.stringify({ history, windowSeconds });
		try {
			sessionStorage.setItem('yue2-gpu-session-v1', value);
		} catch {
			/* History is optional. */
		}
	});
	$effect(() => {
		if (!active || !visible) return;
		let stopped = false;
		let timer: ReturnType<typeof setTimeout>;
		const controller = new AbortController();
		async function poll() {
			try {
				const res = await fetch('system/gpu', {
					cache: 'no-store',
					signal: AbortSignal.any([controller.signal, AbortSignal.timeout(4000)])
				});
				if (!res.ok) throw new Error('GPU telemetry is unavailable in this server.');
				const data: GpuSnapshot = await res.json();
				if (stopped) return;
				gpus = data.gpus;
				message = data.message || 'No NVIDIA GPU was reported.';
				stale = false;
				now = Date.now();
				const merged = new Map(history.map((s) => [`${s.index}:${s.timestamp}`, s]));
				for (const sample of data.history)
					merged.set(`${sample.index}:${sample.timestamp}`, sample);
				history = [...merged.values()]
					.filter((s) => s.timestamp >= now - 600000 && s.timestamp <= now + 5000)
					.sort((a, b) => a.timestamp - b.timestamp)
					.slice(-19200);
			} catch {
				if (!stopped) {
					stale = true;
					message =
						'GPU telemetry is temporarily unavailable. Check the container and NVIDIA driver.';
				}
			} finally {
				if (!stopped) timer = setTimeout(poll, 1000);
			}
		}
		poll();
		return () => {
			stopped = true;
			controller.abort();
			clearTimeout(timer);
		};
	});
</script>

<section class="surface gpu-monitor">
	<div class="monitor-heading">
		<h2 class="section-heading"><Activity size={19} /> GPU monitor</h2>
		<div class="window-picker" aria-label="History window" role="group">
			<button
				type="button"
				class:chosen={windowSeconds === 60}
				aria-pressed={windowSeconds === 60}
				onclick={() => (windowSeconds = 60)}>1 min</button
			><button
				type="button"
				class:chosen={windowSeconds === 600}
				aria-pressed={windowSeconds === 600}
				onclick={() => (windowSeconds = 600)}>10 min</button
			>
		</div>
	</div>
	<p class="field-help">
		{stale
			? 'Connection interrupted. Last valid readings are retained.'
			: 'Live while System is visible. No background sampling when you leave.'}
	</p>
	{#each gpus as gpu}
		<div class="gpu-heading">
			<Cpu size={18} />
			<h3>{gpu.name}</h3>
			<span>GPU {gpu.index}</span>
		</div>
		<div class="metric-grid">
			{#each metrics as metric}
				{#if gpu[metric.key] != null}
					<GpuChart
						label={metric.label}
						unit={metric.unit}
						points={history
							.filter((s) => s.index === gpu.index && s[metric.key] != null)
							.map((s) => ({ timestamp: s.timestamp, value: s[metric.key]! }))}
						maximum={'max' in metric ? metric.max : gpu[metric.maxKey]}
						{windowSeconds}
						{now}
					/>
				{/if}
			{/each}
		</div>
		<div class="gpu-details">
			<span
				>VRAM {gpu.memory_total_mb == null
					? 'N/A'
					: `${(gpu.memory_total_mb / 1024).toFixed(1)} GiB`}</span
			><span>State {gpu.performance_state == null ? 'N/A' : `P${gpu.performance_state}`}</span><span
				>PCIe {gpu.pcie_generation == null
					? 'N/A'
					: `Gen ${gpu.pcie_generation} ×${gpu.pcie_width ?? '?'}`}</span
			><span
				>Power limit {gpu.power_limit_w == null ? 'N/A' : `${gpu.power_limit_w.toFixed(0)} W`}</span
			>
		</div>
	{:else}<div class="gpu-empty">
			<Cpu size={28} /><strong>GPU telemetry unavailable</strong>
			<p>{message}</p>
		</div>{/each}
</section>

<style>
	.monitor-heading {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
	}
	.window-picker {
		display: flex;
		border: 1px solid var(--border);
		border-radius: 5px;
		overflow: hidden;
	}
	.window-picker button {
		padding: 6px 9px;
		border: 0;
		background: transparent;
		color: var(--fg-dim);
		font-size: 0.65rem;
	}
	.window-picker .chosen {
		background: var(--bg-btn-hover);
		color: var(--fg);
	}
	.gpu-heading {
		display: flex;
		align-items: center;
		gap: 8px;
		margin: 25px 0 16px;
	}
	.gpu-heading :global(svg) {
		color: var(--accent);
	}
	.gpu-heading h3 {
		flex: 1;
		font-size: 0.8rem;
		overflow-wrap: anywhere;
	}
	.gpu-heading span {
		color: var(--fg-dim);
		font-size: 0.65rem;
		white-space: nowrap;
	}
	.metric-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 12px;
	}
	.gpu-details {
		display: flex;
		flex-wrap: wrap;
		gap: 7px 14px;
		margin-top: 15px;
		font-size: 0.62rem;
		color: var(--fg-dim);
	}
	.gpu-empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 12px;
		padding: 40px 16px;
		color: var(--fg-dim);
		text-align: center;
	}
	.gpu-empty strong {
		color: var(--fg);
		font-size: 0.8rem;
	}
	.gpu-empty p {
		max-width: 360px;
		margin: 0;
		font-size: 0.75rem;
		line-height: 1.6;
	}
	@media (max-width: 540px) {
		.metric-grid {
			grid-template-columns: 1fr;
		}
		.monitor-heading {
			flex-wrap: wrap;
		}
	}
</style>
