import type { Yue2Request, Yue2Props, Song } from './types.js';
import { OUTPUT_FORMATS } from './config.js';
import { emptyRequest } from './fields.js';
import type { InputMode } from './generation.js';
import { editablePrompt } from './generation.js';
import { clearCompositionInputs } from './lyrics.js';

const STORAGE_KEY = 'yue2';

interface Saved {
	editorVersion: number;
	name: string;
	volume: number;
	format: string;
	logsOpen: boolean;
	request: Yue2Request;
	srcSongId: number | null;
}

function load(): Saved {
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (raw) {
			const parsed = JSON.parse(raw);
			return {
				editorVersion: 2,
				name: parsed.name || '',
				volume: parsed.volume ?? 0.5,
				format: OUTPUT_FORMATS.includes(parsed.format) ? parsed.format : 'mp3',
				logsOpen: parsed.logsOpen ?? true,
				request: parsed.request
					? parsed.editorVersion === 2
						? parsed.request
						: editablePrompt(parsed.request)
					: emptyRequest(),
				srcSongId: parsed.srcSongId ?? null
			};
		}
	} catch {
		// corrupt or unavailable
	}
	return {
		editorVersion: 2,
		name: '',
		volume: 0.5,
		format: 'mp3',
		logsOpen: true,
		request: emptyRequest(),
		srcSongId: null
	};
}

const saved = load();

export const app = $state({
	name: saved.name,
	volume: saved.volume,
	format: saved.format,
	logsOpen: saved.logsOpen,
	request: {
		...emptyRequest(),
		...saved.request,
		abc_sampling: { ...saved.request.abc_sampling },
		semantic_sampling: { ...saved.request.semantic_sampling }
	} as Yue2Request,
	songs: [] as Song[],
	props: null as Yue2Props | null,
	toast: '' as string,
	toastOk: false,
	generating: false,
	srcSongId: null as number | null,
	inputMode: 'fresh' as InputMode
});

let toastTimer = 0;

export function toast(msg: string, ms = 4000, ok = false) {
	clearTimeout(toastTimer);
	app.toast = msg;
	app.toastOk = ok;
	toastTimer = setTimeout(() => {
		app.toast = '';
	}, ms) as unknown as number;
}

// overwrite app.request. A release is two GGUF fixed at server startup, so
// there is no routing to preserve across a load. An incoming request is
// sparse, every field left at its default being absent, so it lands on top of
// an empty one: a field the sender omitted reads back as unset instead of
// missing, which is what the form binds to.
export function setRequest(incoming: Yue2Request) {
	app.inputMode = 'fresh';
	app.srcSongId = null;
	const base = emptyRequest();
	app.request = {
		...base,
		...incoming,
		abc_sampling: { ...base.abc_sampling, ...incoming.abc_sampling },
		semantic_sampling: { ...base.semantic_sampling, ...incoming.semantic_sampling }
	};
}

export function setInputMode(mode: InputMode) {
	// Resolved seeds loaded for a replay belong only to that performance.
	if (app.inputMode === 'replay' && mode !== 'replay') {
		app.request.lm_seed = undefined;
		app.request.seed = undefined;
	}
	if (mode === 'fresh') clearCompositionInputs(app.request);
	if (mode !== 'source') app.srcSongId = null;
	app.inputMode = mode;
}

// persist on every change
$effect.root(() => {
	$effect(() => {
		const data: Saved = {
			editorVersion: 2,
			name: app.name,
			volume: app.volume,
			format: app.format,
			logsOpen: app.logsOpen,
			request: app.request,
			srcSongId: app.srcSongId
		};
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
		} catch {
			/* Keep the UI usable when storage is unavailable. */
		}
	});
});
