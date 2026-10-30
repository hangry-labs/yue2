<script lang="ts">
	import { tick } from 'svelte';
	import {
		Activity,
		AudioLines,
		BookOpen,
		ChevronDown,
		ChevronUp,
		Github,
		Mail,
		Sparkles
	} from '@lucide/svelte';
	import { app } from '../lib/state.svelte.js';
	import { ui } from '../lib/ui.svelte.js';
	import labsLogo from '../assets/hangrylabs_logo.webp';
	import musicMark from '../assets/yue2-mark.svg';

	let hero: HTMLElement;
	let animation: Animation | undefined;
	const version = __YUE2_VERSION__.split(' ')[0];
	let model = $derived(app.props?.model.split(/[/\\]/).pop() || 'Waiting for local service');
	let status = $derived(
		!app.props ? 'Service unavailable' : app.generating ? 'Generating music' : 'Service ready'
	);
	async function toggle() {
		animation?.cancel();
		const start = hero.getBoundingClientRect().height;
		ui.collapsed = !ui.collapsed;
		await tick();
		const end = hero.getBoundingClientRect().height;
		if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
			animation = hero.animate(
				[
					{ height: `${start}px`, overflow: 'hidden' },
					{ height: `${end}px`, overflow: 'hidden' }
				],
				{ duration: 190, easing: 'ease-out' }
			);
		}
	}
</script>

<header class="brand-hero" class:collapsed={ui.collapsed} bind:this={hero} id="brand-hero">
	<div class="labs-branding">
		<a
			class="labs-signature"
			href="https://hangrylabs.app/"
			target="_blank"
			rel="noreferrer"
			aria-label="Hangry Labs home"
		>
			<span class="powered-label">Powered by</span><img
				src={labsLogo}
				alt="Hangry Labs"
				width="80"
				height="80"
			/>
		</a>
		<a
			class="brand-contact"
			href="mailto:contact@hangrylabs.app"
			aria-label="Contact Hangry Labs at contact@hangrylabs.app"
		>
			<Mail size={18} /><span class="contact-copy"
				><span>Contact us:</span><strong>contact@hangrylabs.app</strong></span
			>
		</a>
	</div>
	<img class="compact-mark" src={musicMark} alt="YuE2" width="44" height="44" />
	<nav class="brand-nav" aria-label="Application links">
		<button class="primary-link" type="button" onclick={() => (ui.examplesOpen = true)}
			><Sparkles size={15} /> Examples</button
		>
		<button type="button" onclick={() => (ui.view = 'api')}><BookOpen size={15} /> API docs</button>
		<button type="button" onclick={() => (ui.view = 'system')}
			><AudioLines size={15} /> Models</button
		>
		<a href="https://github.com/hangry-labs/yue2" target="_blank" rel="noreferrer"
			><Github size={15} /> GitHub</a
		>
	</nav>
	<div class="brand-copy">
		<div class="product-wordmark">
			<img src={musicMark} alt="" width="72" height="72" />
			<h1>YuE<span>2</span></h1>
		</div>
		<p>Your words. Your music. Your machine.</p>
		<span class="product-description">Local song generation studio</span>
	</div>
	<div class="runtime-badge" class:ready={!!app.props} role="status" aria-live="polite">
		<Activity size={20} class={app.generating ? 'pulse' : ''} />
		<div class="runtime-copy"><strong>{status}</strong><span title={model}>{model}</span></div>
		<a
			class="runtime-version"
			href="https://github.com/hangry-labs/yue2/releases"
			target="_blank"
			rel="noreferrer"
			title="YuE2 releases">v{version}</a
		>
	</div>
	<button
		class="hero-toggle"
		type="button"
		aria-controls="brand-hero"
		aria-expanded={!ui.collapsed}
		aria-label={ui.collapsed ? 'Expand header' : 'Collapse header'}
		title={ui.collapsed ? 'Expand header' : 'Collapse header'}
		onclick={toggle}
	>
		{#if ui.collapsed}<ChevronDown size={16} />{:else}<ChevronUp size={16} />{/if}
	</button>
</header>
