<script lang="ts">
	import { Info } from '@lucide/svelte';
	let { title, text }: { title: string; text: string } = $props();
	const id = $props.id();
	let trigger: HTMLButtonElement;
	let panel: HTMLDivElement;
	function position(event: ToggleEvent) {
		if (event.newState !== 'open') return;
		const rect = trigger.getBoundingClientRect();
		const width = Math.min(280, window.innerWidth - 32);
		panel.style.left = `${Math.max(16, Math.min(rect.left, window.innerWidth - width - 16))}px`;
		const height = panel.getBoundingClientRect().height || 210;
		panel.style.top = `${Math.max(16, Math.min(rect.bottom + 6, window.innerHeight - height - 16))}px`;
	}
</script>

<button
	type="button"
	class="setting-help"
	aria-label={`About ${title}`}
	popovertarget={id}
	bind:this={trigger}><Info size={14} aria-hidden="true" /></button
>
<div
	{id}
	popover
	class="help-panel"
	role="note"
	aria-label={`${title} help`}
	bind:this={panel}
	onbeforetoggle={position}
	ontoggle={position}
>
	<strong>{title}</strong>
	<p>{text}</p>
</div>

<style>
	.setting-help {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		min-height: 24px;
		padding: 3px;
		border: none;
		border-radius: 50%;
		background: transparent;
		color: var(--fg-dim);
		cursor: pointer;
		flex-shrink: 0;
	}
	.setting-help:hover {
		color: var(--fg);
		background: var(--bg-input);
	}
	.setting-help:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 2px;
	}
	.help-panel {
		position: fixed;
		inset: auto;
		margin: 0;
		box-sizing: border-box;
		width: min(280px, calc(100vw - 32px));
		max-height: calc(100dvh - 32px);
		overflow: auto;
		padding: 14px 16px;
		border: 1px solid var(--border);
		border-radius: 10px;
		background: var(--rail);
		color: var(--fg);
		box-shadow: 0 12px 40px #0008;
		font: 0.8rem/1.5 var(--font-body, sans-serif);
	}
	strong {
		font-size: 0.8rem;
	}
	p {
		margin: 6px 0 0;
		color: var(--fg-dim);
	}
</style>
