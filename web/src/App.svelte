<script lang="ts">
	import { Music2, Library, Code2, Settings2, ShieldCheck } from '@lucide/svelte';
	import { app, toast } from './lib/state.svelte.js';
	import { ui, type View } from './lib/ui.svelte.js';
	import { props } from './lib/api.js';
	import { getAllSongs } from './lib/db.js';
	import { PROPS_POLL_MS } from './lib/config.js';
	import BrandHeader from './components/BrandHeader.svelte';
	import RequestForm from './components/RequestForm.svelte';
	import SongList from './components/SongList.svelte';
	import SystemView from './components/SystemView.svelte';
	import ApiView from './components/ApiView.svelte';
	import ExamplesDialog from './components/ExamplesDialog.svelte';
	import Toast from './components/Toast.svelte';
	import './theme.css';

	const tabs = [
		{ id: 'create', label: 'Create', icon: Music2 },
		{ id: 'library', label: 'Library', icon: Library },
		{ id: 'api', label: 'API', icon: Code2 },
		{ id: 'system', label: 'System', icon: Settings2 }
	] as const;

	$effect(() => {
		getAllSongs()
			.then((songs) => (app.songs = songs.reverse()))
			.catch(() => toast('Saved songs could not be opened. Check browser storage permissions.'));
	});

	$effect(() => {
		let stopped = false;
		let timer: ReturnType<typeof setTimeout>;
		async function poll() {
			try {
				const value = await props();
				if (!stopped) app.props = value;
			} catch {
				if (!stopped) app.props = null;
			} finally {
				if (!stopped) timer = setTimeout(poll, PROPS_POLL_MS);
			}
		}
		poll();
		return () => {
			stopped = true;
			clearTimeout(timer);
		};
	});

	function tabKeys(event: KeyboardEvent) {
		const index = tabs.findIndex((tab) => tab.id === ui.view);
		let next = index;
		if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
		else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
		else if (event.key === 'Home') next = 0;
		else if (event.key === 'End') next = tabs.length - 1;
		else return;
		event.preventDefault();
		ui.view = tabs[next].id as View;
		document.getElementById(`tab-${ui.view}`)?.focus();
	}
</script>

<a class="skip-link" href="#workspace">Skip to workspace</a>
<BrandHeader />
<div class="app-tabs" role="tablist" aria-label="Music studio views">
	{#each tabs as tab}
		<button
			id={`tab-${tab.id}`}
			type="button"
			role="tab"
			aria-selected={ui.view === tab.id}
			aria-controls={tab.id === 'create' || tab.id === 'library'
				? 'panel-studio'
				: `panel-${tab.id}`}
			tabindex={ui.view === tab.id ? 0 : -1}
			class:active={ui.view === tab.id}
			onclick={() => (ui.view = tab.id)}
			onkeydown={tabKeys}
		>
			<tab.icon size={16} />
			{tab.label}
			{#if tab.id === 'library' && app.songs.length}<span class="tab-count">{app.songs.length}</span
				>{/if}
		</button>
	{/each}
	<span class="tabs-note"><ShieldCheck size={14} /> Local generation</span>
</div>
<main id="workspace" tabindex="-1">
	<!-- Keep authoring and playback mounted across views, including active jobs. -->
	<div
		id="panel-studio"
		role="tabpanel"
		aria-labelledby={`tab-${ui.view === 'library' ? 'library' : 'create'}`}
		hidden={ui.view !== 'create' && ui.view !== 'library'}
	>
		<RequestForm library={ui.view === 'library'}
			><SongList library={ui.view === 'library'} /></RequestForm
		>
	</div>
	<div id="panel-api" role="tabpanel" aria-labelledby="tab-api" hidden={ui.view !== 'api'}>
		<ApiView />
	</div>
	<div id="panel-system" role="tabpanel" aria-labelledby="tab-system" hidden={ui.view !== 'system'}>
		<SystemView active={ui.view === 'system'} />
	</div>
</main>
<footer class="app-footer">
	<span>YuE2 by MAP · Native engine by yue2.cpp</span><span
		>48 kHz stereo · Weights stay on your machine</span
	>
</footer>
<ExamplesDialog />
<Toast />
