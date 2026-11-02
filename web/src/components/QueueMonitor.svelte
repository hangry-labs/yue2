<script lang="ts">
	import { onMount } from 'svelte';
	import { ListOrdered, HardDrive } from '@lucide/svelte';
	import type { RuntimeStatus } from '../lib/types.js';
	let { active }: { active: boolean } = $props();
	let visible = $state(!document.hidden);
	let status = $state<RuntimeStatus | null>(null);
	let stale = $state(false);
	const bytes = (n: number) => `${(n / 1024 ** 3).toFixed(2)} GiB`;
	onMount(() => {
		const changed = () => (visible = !document.hidden);
		document.addEventListener('visibilitychange', changed);
		return () => document.removeEventListener('visibilitychange', changed);
	});
	$effect(() => {
		if (!active || !visible) return;
		let stopped = false;
		let timer: ReturnType<typeof setTimeout>;
		const controller = new AbortController();
		async function poll() {
			try {
				const response = await fetch('system/queue', {
					cache: 'no-store',
					signal: AbortSignal.any([controller.signal, AbortSignal.timeout(4000)])
				});
				if (!response.ok) throw new Error('Queue status unavailable');
				const data: RuntimeStatus = await response.json();
				if (!stopped) {
					status = data;
					stale = false;
				}
			} catch {
				if (!stopped) stale = true;
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

<section class="surface queue-monitor">
	<h3 class="section-heading"><ListOrdered size={17} /> Generation queue</h3>
	<p class="field-help" role="status">
		{#if stale}Queue status unavailable. Last readings may be out of date.
		{:else if status}{status.queue.accepting ? 'Ready for requests' : 'Queue full — retry shortly'}
		{:else}Connecting to the local queue…{/if}
	</p>
	{#if status}
		<dl>
			<dt>Generating</dt>
			<dd>{status.queue.active} / 1</dd>
			<dt>Waiting</dt>
			<dd>{status.queue.queued}</dd>
			<dt>Capacity</dt>
			<dd>{status.queue.pending} / {status.queue.limit} jobs</dd>
			<dt>Available</dt>
			<dd>{status.queue.available} slots</dd>
			<dt>Rejected</dt>
			<dd>{status.queue.rejected} since startup</dd>
		</dl>
		<p class="field-help">
			Studio, API and agent requests share one queue. A full queue asks callers to retry after {status
				.queue.retry_after_seconds} seconds.
		</p>
		<h3 class="section-heading storage-heading"><HardDrive size={17} /> Server results</h3>
		<dl>
			<dt>Saved results</dt>
			<dd>{status.results.files} / {status.results.limit_files}</dd>
			<dt>Volume usage</dt>
			<dd>{bytes(status.results.bytes)} / {bytes(status.results.limit_bytes)}</dd>
			<dt>Retention</dt>
			<dd>{(status.results.ttl_seconds / 3600).toLocaleString()} hours</dd>
		</dl>
		<p class="field-help">
			Completed Studio and API results are saved on the output volume and survive restarts until
			expiry. Browser library copies are separate. Agent download links last one hour.
		</p>
		{#if status.results.full}<p class="storage-full" role="status">
				Result storage is full. New results will need space or a higher storage limit.
			</p>{/if}
	{/if}
</section>

<style>
	dl {
		display: grid;
		grid-template-columns: minmax(100px, 1fr) minmax(0, 1fr);
		gap: 12px;
		margin: 20px 0;
		font-size: 0.73rem;
	}
	dt {
		color: var(--fg-dim);
	}
	dd {
		margin: 0;
		overflow-wrap: anywhere;
	}
	.field-help {
		margin-top: 14px;
	}
	.storage-heading {
		margin-top: 24px;
	}
	.storage-full {
		color: var(--error);
		font-size: 0.74rem;
		margin-top: 12px;
	}
</style>
