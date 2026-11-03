<script lang="ts">
	import { msg } from '../lib/i18n.svelte.js';
	import { language, LOCALES, setLocale } from '../lib/i18n.svelte.js';
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
	import musicMark from '../assets/yue2_favicon.webp';
	import productLogo from '../assets/yue2_logo_horizontal.webp';

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
			aria-label={msg('Hangry Labs home')}
		>
			<span class="powered-label">{msg('Powered by')}</span><img
				src={labsLogo}
				alt="Hangry Labs"
				width="80"
				height="80"
			/>
		</a>
		<a
			class="brand-contact"
			href="mailto:contact@hangrylabs.app"
			aria-label={msg('Contact Hangry Labs at {email}', { email: 'contact@hangrylabs.app' })}
		>
			<Mail size={18} /><span class="contact-copy"
				><span>{msg('Contact us:')}</span><strong>contact@hangrylabs.app</strong></span
			>
		</a>
	</div>
	<img class="compact-mark" src={musicMark} alt="YuE2" width="44" height="44" />
	<nav class="brand-nav" aria-label={msg('Application links')}>
		<button class="primary-link" type="button" onclick={() => (ui.examplesOpen = true)}
			><Sparkles size={15} /> {msg('Examples')}</button
		>
		<button type="button" onclick={() => (ui.view = 'api')}
			><BookOpen size={15} /> {msg('API docs')}</button
		>
		<button type="button" onclick={() => (ui.view = 'system')}
			><AudioLines size={15} /> {msg('Models')}</button
		>
		<label class="locale-picker">
			<span class="sr-only">{msg('Interface language')}</span>
			<select
				aria-label={msg('Interface language')}
				value={language.code}
				onchange={(event) => setLocale(event.currentTarget.value)}
			>
				{#each LOCALES as locale}<option value={locale.code} lang={locale.code}
						>{locale.name}</option
					>{/each}
			</select>
		</label>
		<a href="https://github.com/hangry-labs/yue2" target="_blank" rel="noreferrer"
			><Github size={15} /> GitHub</a
		>
	</nav>
	<div class="brand-copy">
		<h1 class="product-wordmark">
			<img src={productLogo} alt="YuE2" width="2172" height="724" />
		</h1>
	</div>
	<div class="runtime-badge" class:ready={!!app.props} role="status" aria-live="polite">
		<Activity size={20} class={app.generating ? 'pulse' : ''} />
		<div class="runtime-copy">
			<strong>{msg(status)}</strong><span title={model}>{msg(model)}</span>
		</div>
		<a
			class="runtime-version"
			href="https://github.com/hangry-labs/yue2/releases"
			target="_blank"
			rel="noreferrer"
			title={msg('YuE2 releases')}>{msg('v')}{version}</a
		>
	</div>
	<button
		class="hero-toggle"
		type="button"
		aria-controls="brand-hero"
		aria-expanded={!ui.collapsed}
		aria-label={ui.collapsed ? msg('Expand header') : msg('Collapse header')}
		title={ui.collapsed ? msg('Expand header') : msg('Collapse header')}
		onclick={toggle}
	>
		{#if ui.collapsed}<ChevronDown size={16} />{:else}<ChevronUp size={16} />{/if}
	</button>
</header>
