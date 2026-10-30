<script lang="ts">
	import type { Snippet } from 'svelte';
	import DialogButton from './DialogButton.svelte';
	let {
		open = $bindable(false),
		title,
		body,
		actions,
		onConfirm
	}: {
		open: boolean;
		title: string;
		body?: Snippet;
		actions?: Snippet<[() => void]>;
		onConfirm?: () => void;
	} = $props();
	let root: HTMLDialogElement;
	function cancel() {
		open = false;
	}
	function confirm() {
		open = false;
		onConfirm?.();
	}
	$effect(() => {
		if (open && !root.open) root.showModal();
		else if (!open && root.open) root.close();
	});
	function outside(event: MouseEvent) {
		if (event.target !== root) return;
		const rect = root.getBoundingClientRect();
		if (
			event.clientX < rect.left ||
			event.clientX > rect.right ||
			event.clientY < rect.top ||
			event.clientY > rect.bottom
		)
			cancel();
	}
</script>

<dialog
	bind:this={root}
	aria-label={title}
	onclose={cancel}
	onmousedown={outside}
	onkeydown={(event) => {
		if (event.key === 'Enter' && !actions && !(event.target instanceof HTMLTextAreaElement)) {
			event.preventDefault();
			confirm();
		}
	}}
>
	<div class="dialog-title">{title}</div>
	{#if body}<div class="dialog-body">{@render body()}</div>{/if}
	<div class="dialog-footer">
		{#if actions}{@render actions(cancel)}{:else}<DialogButton onclick={cancel}>Cancel</DialogButton
			><DialogButton onclick={confirm}>OK</DialogButton>{/if}
	</div>
</dialog>

<style>
	dialog {
		width: min(90vw, 440px);
		max-height: 85dvh;
		padding: 22px;
		background: var(--bg-card);
		color: var(--fg);
		border: 1px solid var(--border);
		border-radius: 8px;
		box-shadow: 0 14px 60px #0005;
	}
	dialog::backdrop {
		background: #0009;
		backdrop-filter: blur(3px);
	}
	.dialog-title {
		font-size: 0.9rem;
		font-weight: 650;
	}
	.dialog-body {
		margin-top: 16px;
		font-size: 0.8rem;
		line-height: 1.6;
	}
	.dialog-footer {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 22px;
	}
</style>
