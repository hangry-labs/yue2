<script lang="ts">
	import { msg } from '../lib/i18n.svelte.js';
	import { onMount, type Snippet } from 'svelte';
	import { parse as yamlParse } from 'yaml';
	import { stringifyYamlRequest } from '../lib/yaml.js';
	import { RotateCcw, Download, FolderOpen, X } from '@lucide/svelte';
	import { app, toast, setRequest, setInputMode } from '../lib/state.svelte.js';
	import { example, applyExample } from '../lib/example.js';
	import {
		synthSubmit,
		pollJob,
		jobResultTracks,
		cancelJob,
		vaeDecode,
		jobResultBlob
	} from '../lib/api.js';
	import { putSong, getAllSongs, saveJob, loadJob, clearJob } from '../lib/db.js';
	import { clearSection, emptyRequest } from '../lib/fields.js';
	import { updateLyrics, clearCompositionInputs } from '../lib/lyrics.js';
	import { generationRequest, inputRequest, variationCount } from '../lib/generation.js';
	import SettingHelp from './SettingHelp.svelte';
	import PlaybackControls from './PlaybackControls.svelte';
	import {
		COT_FULL,
		COT_MELODY,
		COT_OFF,
		INPUT_AUDIO_FORMATS,
		OUTPUT_FORMATS,
		audioMime
	} from '../lib/config.js';
	import type { Yue2Request, Song } from '../lib/types.js';
	import type { PendingJob } from '../lib/db.js';
	import Dialog from './Dialog.svelte';
	import DialogButton from './DialogButton.svelte';

	let { library = false, children }: { library?: boolean; children?: Snippet } = $props();
	let busy = $state(false);
	let mobileSettingsOpen = $state(false);
	$effect(() => {
		app.generating = busy;
	});
	let fileInput: HTMLInputElement;
	let saveFormatOpen = $state(false);

	let d = $derived(app.props?.defaults);
	let outputFormats = $derived(
		app.props?.output_formats?.map((format) => format.name) ?? OUTPUT_FORMATS
	);

	// The adapter directory of the server. The stacked list grows one menu at
	// a time: an adapter picked in the trailing menu opens another, Disabled
	// takes its row out.
	let adapterList = $derived(app.props?.adapters ?? []);
	let adapterRows = $derived([...(app.request.adapters ?? []), { name: '' }]);

	function pickAdapter(i: number, name: string) {
		const list = app.request.adapters ?? [];
		if (!name) list.splice(i, 1);
		else if (i < list.length) list[i].name = name;
		else list.push({ name });
		app.request.adapters = list;
	}

	function halves(e: { ar: boolean; nar: boolean }): string {
		return e.ar && e.nar ? 'AR + NAR' : e.ar ? 'AR' : 'NAR';
	}

	// The mode menu shows the published default until a mode is picked, so
	// the request carries a cot only when it is yours.
	let cot = $derived(app.request.cot || d?.cot || '');

	// resume a pending job after page reload, or land a fresh submission.
	// shared tail of both the onMount resume and the generate path.
	async function landJob(job: PendingJob) {
		await pollJob(job.id);
		const tracks = await jobResultTracks(job.id);
		clearJob();
		// one card per track. The card keeps the track's replay request:
		// the score, the semantic stream and the exact seed.
		const now = Date.now();
		for (let i = 0; i < tracks.length; i++) {
			const r = tracks[i].request;
			const song: Song = {
				name: tracks.length > 1 ? `${job.name} ${i}` : job.name,
				format: app.format,
				created: now + i,
				style: r.style || '',
				seed: r.lm_seed ?? 0,
				duration: 0,
				score: r.abc || '',
				request: r,
				audio: tracks[i].audio,
				latents: tracks[i].latents
			};
			song.id = await putSong(song);
		}
		app.songs = (await getAllSongs()).reverse();
	}

	function editLyrics(value: string) {
		if (value === (app.request.lyrics || '')) return;
		updateLyrics(app.request, value);
		app.srcSongId = null;
		setInputMode('fresh');
	}

	function editStyle(value: string) {
		if (value === app.request.style) return;
		app.request.style = value;
		clearCompositionInputs(app.request);
		app.srcSongId = null;
		setInputMode('fresh');
	}

	// on mount: resume polling for a pending job in localStorage.
	onMount(() => {
		const job = loadJob();
		if (job) {
			busy = true;
			landJob(job)
				.catch(() => {
					clearJob();
				})
				.finally(() => {
					busy = false;
				});
		}
	});

	function reset() {
		app.name = '';
		setRequest(emptyRequest());
	}

	function saveAs(format: 'json' | 'yaml') {
		const req = buildRequest();
		let text: string;
		try {
			text = format === 'json' ? JSON.stringify(req, null, 2) : stringifyYamlRequest(req);
		} catch {
			toast('Could not preserve this request in YAML. Try saving as JSON.');
			return;
		}
		const mime = format === 'json' ? 'application/json' : 'application/x-yaml';
		const blob = new Blob([text], { type: mime });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		const safe = app.name.replace(/[\\/:*?"<>|\x00-\x1f]/g, '') || 'request';
		a.download = `${safe}.${format}`;
		a.click();
		URL.revokeObjectURL(url);
	}

	function importJson() {
		fileInput.click();
	}

	function onFileSelected(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		// reset so the same file can be re-opened
		input.value = '';

		const ext = file.name.split('.').pop()?.toLowerCase() || '';

		// MP3 or WAV: a song card with the audio alone, transcribed from the
		// card into a score
		if (INPUT_AUDIO_FORMATS.includes(ext)) {
			openAudio(file, ext);
			return;
		}

		// VAE latents: decoded through /vae into the audio, a card holding
		// both from the start
		if (ext === 'vae') {
			openLatents(file);
			return;
		}

		// JSON and YAML share the same load path: parse, push the request into
		// the form, and use the file basename as app.name.
		const parsers: Record<string, (s: string) => Yue2Request> = {
			json: JSON.parse,
			yml: yamlParse,
			yaml: yamlParse
		};
		const parse = parsers[ext];
		if (!parse) {
			toast('Unsupported file type: ' + ext);
			return;
		}
		file
			.text()
			.then((text) => {
				const parsed = parse(text) as any;

				// optional title field: lets a LLM authored YAML/JSON pre-fill
				// the song name on import. Stripped before setRequest.
				const importedName =
					typeof parsed?.title === 'string' && parsed.title.trim() ? parsed.title.trim() : '';
				delete parsed.title;
				setRequest(parsed as Yue2Request);
				app.name = importedName || file.name.replace(/\.(json|ya?ml)$/i, '') || 'Imported';
			})
			.catch(() => {
				toast(`Invalid ${ext.toUpperCase()} file`);
			});
	}

	// open audio file: create song card with audio only (no server call).
	// use Transcribe on the card to read its score.
	async function openAudio(file: File, ext: string) {
		const blob = new Blob([await file.arrayBuffer()], {
			type: audioMime(ext)
		});
		const name = file.name.slice(0, -(ext.length + 1)) || 'Imported';
		const song: Song = {
			name,
			format: ext,
			created: Date.now(),
			style: '',
			seed: 0,
			duration: 0,
			score: '',
			request: emptyRequest(),
			audio: blob
		};
		song.id = await putSong(song);
		app.songs.unshift(song);
		app.name = name;
		toast('Opened: ' + name, 4000, true);
	}

	// open VAE latents file: check the framing, decode it through /vae, then
	// create a card with the audio and the latents, the latents a retouch
	// starts from
	async function openLatents(file: File) {
		const buf = await file.arrayBuffer();
		const T = buf.byteLength / 256;
		if (buf.byteLength === 0 || buf.byteLength % 256 !== 0) {
			toast('Invalid .vae file: size must be a multiple of 256 bytes (64 channels x f32)');
			return;
		}
		if (app.props && T > app.props.context) {
			toast(`Invalid .vae file: longer than the context (${app.props.context} frames)`);
			return;
		}
		const latents = new Blob([buf], { type: 'application/octet-stream' });
		const name = file.name.replace(/\.vae$/i, '') || 'Imported';
		try {
			const jobId = await vaeDecode(latents, buildRequest(), app.format);
			await pollJob(jobId);
			const song: Song = {
				name,
				format: app.format,
				created: Date.now(),
				style: '',
				seed: 0,
				duration: 0,
				score: '',
				request: emptyRequest(),
				audio: await jobResultBlob(jobId),
				latents
			};
			song.id = await putSong(song);
			app.songs.unshift(song);
			app.name = name;
			toast('Opened: ' + name, 4000, true);
		} catch (e: unknown) {
			toast(e instanceof Error ? e.message : String(e));
		}
	}

	// snapshot app.request into a clean Yue2Request with proper types.
	// bind:value guarantees app.request always matches the DOM.
	function buildRequest(): Yue2Request {
		return inputRequest(app.request, app.inputMode);
	}

	// Example: pick a random official demo prompt, fill the form and name
	// the song after it
	function pickExample() {
		const ex = example();
		applyExample(ex);
	}

	// Generate: submit the request, poll until done, land the song card.
	// The webui resolves the seeds so the stored request reproduces the song.
	async function generate() {
		busy = true;
		try {
			const req = generationRequest(app.request, app.inputMode);
			// An adapter the server no longer lists stays visible in its menu
			// and out of the run
			req.adapters = req.adapters?.filter((a) => adapterList.some((e) => e.name === a.name));
			// A source card opens the song with its section: its codes ride in
			// source_tokens, kept on the card by its generation or by
			// Tokenize audio
			const src =
				app.inputMode === 'source' && app.srcSongId != null
					? app.songs.find((s) => s.id === app.srcSongId)
					: null;
			if (src && !src.request.semantic_tokens) {
				toast('Tokenize audio on the source card first');
				return;
			}
			if (src) {
				req.source_tokens = src.request.semantic_tokens;
				req.semantic_tokens = undefined;
			}
			if (app.inputMode === 'replay' && !req.semantic_tokens?.trim())
				throw new Error('Choose a take from the library to replay, or supply audio codes.');
			if (app.inputMode === 'source' && !req.source_tokens?.trim())
				throw new Error('Select a source song in the library first.');
			if (app.inputMode === 'score' && !req.abc?.trim())
				throw new Error('Enter an ABC score or choose a score from the library.');
			const jobId = await synthSubmit(req, app.format);
			const job: PendingJob = { id: jobId, name: app.name || 'Untitled', request: req };
			saveJob(job);
			await landJob(job);
		} catch (e: unknown) {
			toast(e instanceof Error ? e.message : String(e));
		} finally {
			busy = false;
		}
	}

	// cancel the active pipeline job
	async function cancelPipeline() {
		try {
			const job = loadJob();
			if (job) await cancelJob(job.id);
		} catch {}
	}

	function clearLm() {
		clearSection(app.request, 'lm');
	}

	function clearScoreSampling() {
		clearSection(app.request, 'score');
	}

	// the score itself, so a generation that missed the tune is one click away
	// from a free composition again
	function clearScoreText() {
		app.request.abc = '';
		if (app.inputMode === 'score') setInputMode('fresh');
	}

	function clearSemantic() {
		clearSection(app.request, 'semantic');
		if (app.inputMode === 'replay') setInputMode('fresh');
	}

	function clearPost() {
		clearSection(app.request, 'post');
	}

	function ph(v: unknown): string {
		return v != null ? String(v) : '';
	}
</script>

<div class="request-form" class:library>
	<input
		type="file"
		accept=".json,.yml,.yaml,.mp3,.wav,.opus,.ogg,.flac,.aac,.m4a,.mp4,.webm,.vae"
		bind:this={fileInput}
		onchange={onFileSelected}
		hidden
	/>
	<aside
		class="settings-rail"
		aria-label={library ? msg('Playback controls') : msg('Playback and generation settings')}
	>
		<PlaybackControls />
		<h2 class="section-heading rail-heading" hidden={library}>{msg('Generation setup')}</h2>
		<button
			type="button"
			class="settings-toggle"
			hidden={library}
			aria-expanded={mobileSettingsOpen}
			aria-controls="generation-settings"
			onclick={() => (mobileSettingsOpen = !mobileSettingsOpen)}
			>{msg('Generation setup')}
			<span>{mobileSettingsOpen ? msg('Hide settings −') : msg('Show settings +')}</span></button
		>
		<div
			id="generation-settings"
			class="rail-content"
			hidden={library}
			class:mobile-collapsed={!mobileSettingsOpen}
		>
			<div class="model-info">
				<strong
					>{app.props?.model.split(/[/\\]/).pop() || msg('Connecting to local service…')}</strong
				><span>{msg('CUDA · 48 kHz stereo')}</span><span
					>{msg('Blank values use the server defaults.')}</span
				>
			</div>
			{#if adapterList.length}
				<details>
					<summary>{msg('Models')}</summary>
					<div class="details-body">
						{#each adapterRows as a, i}
							<div class="field-row">
								<div class="setting-label">
									<label class="field-label" for={`adapter-${i}`}>{msg('LoRA')}</label><SettingHelp
										title={msg('LoRA')}
										text={msg(
											'An optional model adapter that biases style or delivery according to its training. Its effect depends on the adapter and may affect composition, sound, or both.'
										)}
									/>
								</div>
								<select
									id={`adapter-${i}`}
									class="field-select"
									value={a.name}
									onchange={(e) => pickAdapter(i, e.currentTarget.value)}
									title={msg(
										'Adapter merged into the halves it changes at load time. Scanned from the --adapters directory: a .safetensors file, or a folder holding one next to its adapter_config.json.'
									)}
								>
									<option value="">{msg('Disabled')}</option>
									{#if a.name && !adapterList.some((e) => e.name === a.name)}
										<option value={a.name} disabled>{a.name}</option>
									{/if}
									{#each adapterList as e}
										<option value={e.name}>{e.name} ({halves(e)})</option>
									{/each}
								</select>
								{#if a.name && app.request.adapters}
									<div class="setting-label">
										<label for={`adapter-strength-${i}`}>{msg('Strength')}</label><SettingHelp
											title={msg('Adapter strength')}
											text={msg(
												'How much the adapter influences the result. 1 applies its normal strength; lower values soften the effect. Higher values can make it stronger but may introduce artifacts.'
											)}
										/>
									</div>
									<input
										id={`adapter-strength-${i}`}
										type="text"
										class="scale-input"
										placeholder="1.0"
										bind:value={app.request.adapters[i].scale}
										title={msg(
											'Adapter strength. Lower it if you hear artifacts, raise it for a stronger effect.'
										)}
									/>
								{/if}
							</div>
						{/each}
					</div>
				</details>
			{/if}
			<div class="section-title section-header">
				{msg('Composition settings')}
				<button
					type="button"
					class="clear-btn"
					title={msg('Clear Composition settings')}
					onclick={clearLm}
					aria-label={msg('Clear Composition settings')}
				>
					<X size={20} />
				</button>
			</div>
			<div class="field-row">
				<div class="setting-label">
					<label for="composition-input">{msg('Composition input')}</label><SettingHelp
						title={msg('Composition input')}
						text={msg(
							'New song composes from the current lyrics and musical direction on every click. Use ABC score deliberately keeps a written tune. Replay audio codes renders an existing performance. Continue source uses the selected library excerpt as the opening.'
						)}
					/>
				</div>
				<select id="composition-input" bind:value={() => app.inputMode, setInputMode}>
					<option value="fresh">{msg('New song')}</option>
					<option value="score">{msg('Use ABC score')}</option>
					<option value="replay">{msg('Replay audio codes')}</option>
					<option value="source">{msg('Continue source')}</option>
				</select>
			</div>
			<div class="field-row">
				<div class="setting-label">
					<label class="field-label" for="composition-mode">{msg('Mode')}</label><SettingHelp
						title={msg('Mode')}
						text={msg(
							'Full composes a score with chords before the performance. Melody uses a score without chords. Off skips the score stage. This changes how the song is planned, rather than its recording format.'
						)}
					/>
				</div>
				<select
					id="composition-mode"
					class="field-select"
					value={cot}
					onchange={(e) => (app.request.cot = e.currentTarget.value)}
					title={msg('What the autoregressive half writes before the codes.')}
				>
					<option value={COT_FULL}>{msg('Full: the score carries the chords')}</option>
					<option value={COT_MELODY}>{msg('Melody: the score carries no chords')}</option>
					<option value={COT_OFF}>{msg('Off: no score, written or supplied')}</option>
				</select>
			</div>
			<div class="meta-grid">
				<div class="setting-field">
					<div class="setting-label">
						<label for="setting-1">{msg('Duration')}</label><SettingHelp
							title={msg('Duration')}
							text={msg(
								'Maximum requested length in seconds. Longer songs take more time and memory; the model may finish earlier. Lyrics and musical structure also influence the length.'
							)}
						/>
					</div>
					<input
						id="setting-1"
						type="text"
						placeholder={ph(d?.duration)}
						bind:value={app.request.duration}
						title={msg('Target length in seconds. The model can end the song earlier.')}
					/>
				</div>
				<div class="setting-field">
					<div class="setting-label">
						<label for="setting-2">{msg('LM batch')}</label><SettingHelp
							title={msg('LM batch')}
							text={msg(
								'Number of independently composed songs from this prompt. More songs give you more alternatives and increase generation time and memory use.'
							)}
						/>
					</div>
					<input
						id="setting-2"
						type="text"
						placeholder={ph(d?.lm_batch_size)}
						bind:value={app.request.lm_batch_size}
						title={msg(
							'Songs drawn from this prompt, each with its own score and codes, seeds LM seed + index.'
						)}
					/>
				</div>
				<div class="setting-field">
					<div class="setting-label">
						<label for="setting-3">{msg('LM seed')}</label><SettingHelp
							title={msg('LM seed')}
							text={msg(
								'Random by default: each click creates a new composition. A fixed nonnegative number helps repeat the melody, phrasing and musical structure with the same inputs. Blank or -1 restores random.'
							)}
						/>
					</div>
					<input
						id="setting-3"
						type="text"
						placeholder={msg('Random')}
						bind:value={app.request.lm_seed}
						title={msg(
							'Seed of the token draw: the score, the melody and the length come from this one.'
						)}
					/>
				</div>
			</div>
			<details class="has-clear">
				<summary>{msg('Score sampling')}</summary>
				<button
					type="button"
					class="clear-btn details-clear"
					title={msg('Clear score sampling')}
					onclick={clearScoreSampling}
					aria-label={msg('Clear score sampling')}
				>
					<X size={20} />
				</button>
				<div class="details-body">
					<div class="meta-grid">
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-4">{msg('Temperature')}</label><SettingHelp
									title={msg('Score: Temperature')}
									text={msg(
										'Randomness of token selection. Higher values allow more surprising choices but can become incoherent; lower values are more predictable. These choices affect the written notes, rhythm and harmony.'
									)}
								/>
							</div>
							<input
								id="setting-4"
								type="text"
								placeholder={ph(d?.abc_sampling?.temperature)}
								bind:value={app.request.abc_sampling.temperature}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-5">{msg('Top P')}</label><SettingHelp
									title={msg('Score: Top P')}
									text={msg(
										'Keeps likely tokens until their combined probability reaches this value. Lower values narrow the choices; values nearer 1 allow more variety. These choices affect the written notes, rhythm and harmony.'
									)}
								/>
							</div>
							<input
								id="setting-5"
								type="text"
								placeholder={ph(d?.abc_sampling?.top_p)}
								bind:value={app.request.abc_sampling.top_p}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-6">{msg('Top K')}</label><SettingHelp
									title={msg('Score: Top K')}
									text={msg(
										'Limits selection to this many likely tokens. Lower values are more conservative; higher values allow more alternatives. Use a positive integer; 1 restricts selection to the most likely token. These choices affect the written notes, rhythm and harmony.'
									)}
								/>
							</div>
							<input
								id="setting-6"
								type="text"
								placeholder={ph(d?.abc_sampling?.top_k)}
								bind:value={app.request.abc_sampling.top_k}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-7">{msg('Repetition penalty')}</label><SettingHelp
									title={msg('Score: Repetition penalty')}
									text={msg(
										'Discourages recently used tokens. Values above 1 can reduce repetitive patterns; too much can disrupt musical consistency or pronunciation. These choices affect the written notes, rhythm and harmony.'
									)}
								/>
							</div>
							<input
								id="setting-7"
								type="text"
								placeholder={ph(d?.abc_sampling?.repetition_penalty)}
								bind:value={app.request.abc_sampling.repetition_penalty}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-8">{msg('Penalty window')}</label><SettingHelp
									title={msg('Score: Penalty window')}
									text={msg(
										'Number of recent tokens checked for repetition. A larger window discourages repeats over a longer span, but can also discourage useful musical motifs. These choices affect the written notes, rhythm and harmony.'
									)}
								/>
							</div>
							<input
								id="setting-8"
								type="text"
								placeholder={ph(d?.abc_sampling?.penalty_window)}
								bind:value={app.request.abc_sampling.penalty_window}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-9">{msg('Min tokens')}</label><SettingHelp
									title={msg('Score: Min tokens')}
									text={msg(
										'Prevents the stage from ending before this many tokens. Raising it can force more material, but may cause repetition or an unnaturally long passage. These choices affect the written notes, rhythm and harmony.'
									)}
								/>
							</div>
							<input
								id="setting-9"
								type="text"
								placeholder={ph(d?.abc_sampling?.min_tokens)}
								bind:value={app.request.abc_sampling.min_tokens}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-10">{msg('Max tokens')}</label><SettingHelp
									title={msg('Score: Max tokens')}
									text={msg(
										'Hard limit for this stage. Higher limits allow more material and cost more time and context; limits that are too low can cut the result short. These choices affect the written notes, rhythm and harmony.'
									)}
								/>
							</div>
							<input
								id="setting-10"
								type="text"
								placeholder={ph(d?.abc_sampling?.max_tokens)}
								bind:value={app.request.abc_sampling.max_tokens}
							/>
						</div>
					</div>
				</div>
			</details>
			<details class="has-clear">
				<summary>{msg('Semantic sampling')}</summary>
				<button
					type="button"
					class="clear-btn details-clear"
					title={msg('Clear semantic sampling')}
					onclick={clearSemantic}
					aria-label={msg('Clear semantic sampling')}
				>
					<X size={20} />
				</button>
				<div class="details-body">
					<div class="meta-grid">
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-11">{msg('CFG scale')}</label><SettingHelp
									title={msg('CFG scale')}
									text={msg(
										'How strongly audio generation follows its conditioning. Higher values may improve adherence but can sound less natural or introduce artifacts. Blank uses the mode-specific default; 1 disables the extra guidance branch and reduces its cost.'
									)}
								/>
							</div>
							<input
								id="setting-11"
								type="text"
								placeholder={ph(d?.cfg_scale)}
								bind:value={app.request.cfg_scale}
								title={msg(
									'Guidance of the stage. Exactly 1 keeps a single branch and halves the cost.'
								)}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-12">{msg('Temperature')}</label><SettingHelp
									title={msg('Performance: Temperature')}
									text={msg(
										'Randomness of token selection. Higher values allow more surprising choices but can become incoherent; lower values are more predictable. These choices affect the sung delivery and musical performance.'
									)}
								/>
							</div>
							<input
								id="setting-12"
								type="text"
								placeholder={ph(d?.semantic_sampling?.temperature)}
								bind:value={app.request.semantic_sampling.temperature}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-13">{msg('Top P')}</label><SettingHelp
									title={msg('Performance: Top P')}
									text={msg(
										'Keeps likely tokens until their combined probability reaches this value. Lower values narrow the choices; values nearer 1 allow more variety. These choices affect the sung delivery and musical performance.'
									)}
								/>
							</div>
							<input
								id="setting-13"
								type="text"
								placeholder={ph(d?.semantic_sampling?.top_p)}
								bind:value={app.request.semantic_sampling.top_p}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-14">{msg('Top K')}</label><SettingHelp
									title={msg('Performance: Top K')}
									text={msg(
										'Limits selection to this many likely tokens. Lower values are more conservative; higher values allow more alternatives. Use a positive integer; 1 restricts selection to the most likely token. These choices affect the sung delivery and musical performance.'
									)}
								/>
							</div>
							<input
								id="setting-14"
								type="text"
								placeholder={ph(d?.semantic_sampling?.top_k)}
								bind:value={app.request.semantic_sampling.top_k}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-15">{msg('Repetition penalty')}</label><SettingHelp
									title={msg('Performance: Repetition penalty')}
									text={msg(
										'Discourages recently used tokens. Values above 1 can reduce repetitive patterns; too much can disrupt musical consistency or pronunciation. These choices affect the sung delivery and musical performance.'
									)}
								/>
							</div>
							<input
								id="setting-15"
								type="text"
								placeholder={ph(d?.semantic_sampling?.repetition_penalty)}
								bind:value={app.request.semantic_sampling.repetition_penalty}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-16">{msg('Penalty window')}</label><SettingHelp
									title={msg('Performance: Penalty window')}
									text={msg(
										'Number of recent tokens checked for repetition. A larger window discourages repeats over a longer span, but can also discourage useful musical motifs. These choices affect the sung delivery and musical performance.'
									)}
								/>
							</div>
							<input
								id="setting-16"
								type="text"
								placeholder={ph(d?.semantic_sampling?.penalty_window)}
								bind:value={app.request.semantic_sampling.penalty_window}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-17">{msg('Min tokens')}</label><SettingHelp
									title={msg('Performance: Min tokens')}
									text={msg(
										'Prevents the stage from ending before this many tokens. Raising it can force more material, but may cause repetition or an unnaturally long passage. These choices affect the sung delivery and musical performance.'
									)}
								/>
							</div>
							<input
								id="setting-17"
								type="text"
								placeholder={ph(d?.semantic_sampling?.min_tokens)}
								bind:value={app.request.semantic_sampling.min_tokens}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-18">{msg('Max tokens')}</label><SettingHelp
									title={msg('Performance: Max tokens')}
									text={msg(
										'Hard limit for this stage. Higher limits allow more material and cost more time and context; limits that are too low can cut the result short. These choices affect the sung delivery and musical performance.'
									)}
								/>
							</div>
							<input
								id="setting-18"
								type="text"
								placeholder={ph(d?.semantic_sampling?.max_tokens)}
								bind:value={app.request.semantic_sampling.max_tokens}
							/>
						</div>
					</div>
					<div class="setting-field">
						<div class="setting-label">
							<label for="setting-19">{msg('Audio codes')}</label><SettingHelp
								title={msg('Audio codes')}
								text={msg(
									'A saved performance in model-token form. Use Replay audio codes to render it again; those codes already contain the singing, so editing lyrics cannot rewrite that performance.'
								)}
							/>
						</div>
						<textarea
							id="setting-19"
							rows="4"
							placeholder={msg(
								'Filled when reusing a rendered song. Do not edit unless you know what you are doing.'
							)}
							bind:value={
								() => app.request.semantic_tokens || '',
								(value) => {
									app.request.semantic_tokens = value;
									setInputMode(value.trim() ? 'replay' : 'fresh');
								}
							}
						></textarea>
					</div>
				</div>
			</details>
			<details class="has-clear">
				<summary>{msg('Advanced and post-processing')}</summary>
				<button
					type="button"
					class="clear-btn details-clear"
					title={msg('Clear advanced and post-processing')}
					onclick={clearPost}
					aria-label={msg('Clear advanced and post-processing')}
				>
					<X size={20} />
				</button>
				<div class="details-body">
					<div class="meta-grid">
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-20">{msg('Steps')}</label><SettingHelp
									title={msg('Steps')}
									text={msg(
										'Acoustic refinement steps. The default is 8 for faster generation. More steps take longer and may refine the sound, with diminishing returns; they do not guarantee better lyrics or a better song.'
									)}
								/>
							</div>
							<input
								id="setting-20"
								type="text"
								placeholder={ph(d?.steps)}
								bind:value={app.request.steps}
								title={msg('Midpoint steps of the acoustic ODE.')}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-21">{msg('Variations')}</label><SettingHelp
									title={msg('Variations')}
									text={msg(
										'Different acoustic renditions of the same composition and musical performance. Two are recommended by default; choose one to use less memory, or three for another take. In our two-minute RTX 5070 Ti benchmark, two improved throughput by 67% over one; three added another 25%. Four added only 11% more throughput, saving about 1.1 seconds per rendition while adding about 0.6 GiB to the sampled device peak, so we cap this at three. These measurements include desktop memory; longer songs and other prompts can use more.'
									)}
								/>
							</div>
							<select
								id="setting-21"
								bind:value={
									() =>
										variationCount(
											app.request.synth_batch_size,
											app.inputMode === 'replay' ? 1 : 2
										),
									(value) => {
										app.request.synth_batch_size = value;
									}
								}
								title={msg('Choose one to three acoustic renditions. Two are recommended.')}
							>
								<option value={1}>{msg('1 variation')}</option>
								<option value={2}>{msg('2 variations (recommended)')}</option>
								<option value={3}>{msg('3 variations')}</option>
							</select>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-22">{msg('Noise seed')}</label><SettingHelp
									title={msg('Noise seed')}
									text={msg(
										'Random by default. This controls acoustic texture rather than the underlying composition. Fix a nonnegative number for repeatable rendering; blank or -1 chooses fresh noise.'
									)}
								/>
							</div>
							<input
								id="setting-22"
								type="text"
								placeholder={msg('Random')}
								bind:value={app.request.seed}
								title={msg(
									'Seed of the acoustic noise. Change it to re-render the same song differently.'
								)}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-23">{msg('Source start')}</label><SettingHelp
									title={msg('Source start')}
									text={msg(
										'Start of the source excerpt in seconds, used only with Continue source. Drag a range on the selected source waveform to choose the musical opening.'
									)}
								/>
							</div>
							<input
								id="setting-23"
								type="text"
								placeholder={ph(d?.source_start)}
								bind:value={app.request.source_start}
								title={msg(
									'Seconds into the Src audio card where the section opening the song starts. Drag on its waveform to set the section.'
								)}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-24">{msg('Source end')}</label><SettingHelp
									title={msg('Source end')}
									text={msg(
										'End of the source excerpt in seconds, used only with Continue source. -1 uses the end of the recording. The model continues after this excerpt.'
									)}
								/>
							</div>
							<input
								id="setting-24"
								type="text"
								placeholder={ph(d?.source_end)}
								bind:value={app.request.source_end}
								title={msg(
									'Seconds into the Src audio card where the section ends and the model writes on, -1 its end.'
								)}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-25">{msg('Peak clip')}</label><SettingHelp
									title={msg('Peak clip')}
									text={msg(
										'Controls loudness normalization by allowing a small fraction of peaks to clip. 0 preserves all peaks; higher values can make the result louder but may distort transients. The default is 10. WAV32 bypasses normalization.'
									)}
								/>
							</div>
							<input
								id="setting-25"
								type="text"
								placeholder={ph(d?.peak_clip)}
								bind:value={app.request.peak_clip}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-26">{msg('MP3 bitrate')}</label><SettingHelp
									title={msg('MP3 bitrate')}
									text={msg(
										'MP3 encoding quality in kilobits per second. Higher values usually preserve more detail and produce larger files. This only affects MP3 output, not the composition.'
									)}
								/>
							</div>
							<input
								id="setting-26"
								type="text"
								placeholder={ph(d?.mp3_bitrate)}
								bind:value={app.request.mp3_bitrate}
							/>
						</div>
						<div class="setting-field">
							<div class="setting-label">
								<label for="setting-27">{msg('Format')}</label><SettingHelp
									title={msg('Format')}
									text={msg(
										'Opus, MP3, Ogg Vorbis and AAC/M4A make smaller, lossy files. Opus uses 96 kb/s VBR; AAC/M4A use 192 kb/s. FLAC stores lossless 24-bit audio. WAV16 and WAV24 are uncompressed; WAV32 preserves raw floating-point audio without normalization. All formats retain 48 kHz stereo.'
									)}
								/>
							</div>
							<select
								id="setting-27"
								bind:value={app.format}
								title={msg(
									'Output audio format. WAV32 outputs raw IEEE float without normalization.'
								)}
							>
								{#each outputFormats as format}
									<option value={format}
										>{format === 'ogg' ? msg('OGG / Vorbis') : format.toUpperCase()}</option
									>
								{/each}
							</select>
						</div>
					</div>
				</div>
			</details>
			<p class="field-help">{msg('Model files and runtime details are in System.')}</p>
		</div>
	</aside>
	<section class="composer" hidden={library} aria-label={msg('Song composition')}>
		<div class="composer-heading">
			<h2>{msg('Compose a song')}</h2>
			<div class="toolbar">
				<button type="button" onclick={importJson} title={msg('Open JSON/YAML prompt')}
					><FolderOpen size={14} /> {msg('Open')}</button
				>
				<button
					type="button"
					onclick={() => (saveFormatOpen = true)}
					title={msg('Save prompt as JSON or YAML')}><Download size={14} /> {msg('Save')}</button
				>
				<button type="button" onclick={reset} title={msg('Reset prompt')}
					><RotateCcw size={14} /> {msg('Reset')}</button
				>
			</div>
		</div>
		<div class="setting-label">
			<label class="section-title" for="song-name">{msg('Song name')}</label><SettingHelp
				title={msg('Song name')}
				text={msg(
					'A library and filename label. It is not sent as musical direction and does not change the generated music.'
				)}
			/>
		</div>
		<input id="song-name" type="text" bind:value={app.name} placeholder={msg('Untitled')} />
		<div class="setting-label">
			<label class="section-title" for="song-style">{msg('Musical direction')}</label><SettingHelp
				title={msg('Musical direction')}
				text={msg(
					'Describe genre, instruments, mood, language and vocal character. Clear, compatible directions tend to work better than conflicting instructions; exact tempo or instrumentation is not guaranteed.'
				)}
			/>
		</div>
		<textarea
			id="song-style"
			rows="3"
			placeholder={msg('English, warm piano pop, expressive female voice, acoustic piano...')}
			bind:value={() => app.request.style, editStyle}
		></textarea>
		<div class="setting-label">
			<label class="section-title" for="song-lyrics">{msg('Lyrics')}</label><SettingHelp
				title={msg('Lyrics')}
				text={msg(
					'Words you want sung. Section labels such as [Verse] and [Chorus] help describe the structure. Leave empty for an instrumental request and describe that in musical direction.'
				)}
			/>
		</div>
		<textarea
			id="song-lyrics"
			rows="11"
			placeholder={'[Verse]\n' + msg('Write your lyrics here...')}
			bind:value={() => app.request.lyrics || '', editLyrics}
		></textarea>
		<details class="score-editor">
			<summary>{msg('Score · optional ABC notation')}</summary>
			<div class="section-title section-header">
				<span class="setting-label"
					>{msg('Score')}
					<SettingHelp
						title={msg('ABC score')}
						text={msg(
							'Optional musical notation for a tune and its chords. Typing here selects Use ABC score. Leave it empty and use New song to let the model compose a fresh score. Generated scores stay with their saved songs.'
						)}
					/></span
				>
				<button
					type="button"
					class="clear-btn"
					title={msg('Clear score')}
					onclick={clearScoreText}
					aria-label={msg('Clear score')}
				>
					<X size={20} />
				</button>
			</div>
			<textarea
				aria-label={msg('ABC score')}
				rows="6"
				placeholder={msg('ABC notation. Leave empty for the model to write a score.') +
					'\nX:1\nL:1/8\nM:4/4\nK:Cmaj\n"C"c2 e2 g2 c\'2|'}
				bind:value={
					() => app.request.abc || '',
					(value) => {
						app.request.abc = value;
						setInputMode(value.trim() ? 'score' : 'fresh');
					}
				}
			></textarea>
		</details>
		<div class="action-row">
			<button
				type="button"
				disabled={busy}
				onclick={pickExample}
				title={msg('Pick a random official demo prompt')}>{msg('Surprise me')}</button
			>
			<button
				type="button"
				class="generate-button"
				disabled={busy || !app.props || !app.request.style.trim()}
				onclick={generate}
				title={msg('Run the full pipeline: score, semantic codes, flow matching, VAE')}
				>{busy ? msg('Generating…') : msg('Generate song')}</button
			>
			<button
				type="button"
				disabled={!busy}
				onclick={cancelPipeline}
				title={msg('Cancel the active job')}>{msg('Cancel')}</button
			>
		</div>
		<div class="generation-status" role="status">
			{busy
				? msg('Generating on your machine. You can browse your library while it runs.')
				: !app.props
					? msg('Local service unavailable. Check the container in System.')
					: !app.request.style.trim()
						? msg('Add a musical direction, or choose an example to get started.')
						: msg('Ready to generate on your machine.')}
		</div>
	</section>
	<div class="result-area">{@render children?.()}</div>
</div>
<Dialog bind:open={saveFormatOpen} title={msg('Save format')}>
	{#snippet actions(close)}
		<DialogButton onclick={close}>{msg('Cancel')}</DialogButton>
		<DialogButton
			onclick={() => {
				saveAs('json');
				close();
			}}>{msg('JSON')}</DialogButton
		>
		<DialogButton
			onclick={() => {
				saveAs('yaml');
				close();
			}}>{msg('YAML')}</DialogButton
		>
	{/snippet}
</Dialog>

<style>
	.request-form {
		display: grid;
		grid-template-columns: minmax(240px, 278px) minmax(0, 1fr);
		align-items: start;
		min-height: 660px;
	}
	.settings-rail {
		grid-column: 1;
		grid-row: 1 / 3;
		display: flex;
		flex-direction: column;
		gap: 16px;
		min-width: 0;
		padding: 16px clamp(14px, 2vw, 22px) 30px;
		background: var(--rail);
		border-right: 1px solid var(--border);
		align-self: stretch;
	}
	.rail-content {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.settings-toggle {
		display: none;
	}
	.model-info {
		display: grid;
		gap: 7px;
		padding-bottom: 17px;
		border-bottom: 1px solid var(--line-soft);
	}
	.model-info strong {
		font-size: 0.77rem;
		overflow-wrap: anywhere;
		font-weight: 600;
	}
	.model-info span {
		font-size: 0.66rem;
		color: var(--fg-dim);
	}
	.composer {
		grid-column: 2;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 20px clamp(18px, 3vw, 38px) 24px;
	}
	.composer-heading {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 15px;
		margin-bottom: 5px;
	}
	.composer-heading h2 {
		margin: 0;
		font-size: 1rem;
	}
	.toolbar {
		display: flex;
		gap: 6px;
	}
	.toolbar button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 5px;
		min-height: 32px;
		padding: 6px 10px;
	}
	.result-area {
		grid-column: 2;
		min-width: 0;
		padding: 0 clamp(18px, 3vw, 40px) 30px;
	}
	.library .result-area {
		max-width: 1250px;
		margin: 0 auto;
		padding: 30px;
	}
	label,
	.setting-field {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 0.72rem;
		color: var(--fg-dim);
	}
	.section-title {
		font-size: 0.75rem;
		color: var(--fg);
		font-weight: 650;
		margin: 2px 0 0;
	}
	.section-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	.has-clear {
		position: relative;
	}
	.details-clear {
		position: absolute;
		top: 10px;
		right: 0;
	}
	.clear-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0;
		min-height: 24px;
		border: none;
		background: transparent;
		color: var(--fg-dim);
		cursor: pointer;
		line-height: 0;
	}
	.clear-btn:hover {
		color: var(--fg);
	}
	textarea,
	input[type='text'],
	select {
		font-family: inherit;
		font-size: 0.8rem;
		color: var(--fg);
		background: var(--bg-input);
		border: 1px solid var(--border);
		border-radius: 5px;
		width: 100%;
	}
	textarea {
		padding: 10px 12px;
	}
	.composer > input {
		font-size: 0.85rem;
	}
	textarea:focus,
	input:focus,
	select:focus {
		outline: 2px solid var(--focus);
		outline-offset: -1px;
	}
	.field-row {
		display: flex;
		flex-direction: column;
		align-items: stretch;
		gap: 7px;
	}
	.setting-label {
		display: flex;
		align-items: center;
		gap: 5px;
		min-height: 24px;
	}
	.setting-label label {
		min-width: 0;
	}
	.field-label {
		font-size: 0.72rem;
		color: var(--fg-dim);
	}
	.field-select {
		flex: 1;
		min-width: 0;
	}
	.scale-input {
		max-width: 100px;
	}
	.meta-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 12px;
	}
	.meta-grid > .setting-field:first-child {
		grid-column: 1 / -1;
	}
	details {
		border-top: 1px solid var(--line-soft);
	}
	details summary {
		cursor: pointer;
		font-size: 0.75rem;
		color: var(--fg);
		font-weight: 650;
		padding: 13px 27px 13px 0;
	}
	.details-body {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 0 0 12px;
	}
	.score-editor {
		border: 1px solid var(--border);
		border-radius: 5px;
		padding: 0 12px;
		background: var(--bg-input);
	}
	.score-editor[open] {
		padding-bottom: 12px;
	}
	.score-editor textarea {
		font-family: monospace;
		margin-top: 8px;
	}
	.action-row {
		display: flex;
		gap: 8px;
		margin-top: 6px;
	}
	.action-row button {
		min-height: 40px;
	}
	.action-row .generate-button {
		flex: 1;
		background: var(--accent);
		border-color: var(--accent);
		color: #211006;
		font-weight: 750;
	}
	.action-row .generate-button:hover:not(:disabled) {
		background: var(--accent-hover);
	}
	button {
		padding: 8px 12px;
		border: 1px solid var(--border);
		border-radius: 5px;
		background: var(--bg-btn);
		color: var(--fg);
		cursor: pointer;
		font-size: 0.75rem;
	}
	button:hover:not(:disabled) {
		background: var(--bg-btn-hover);
	}
	button:disabled {
		opacity: 0.45;
	}
	.generation-status {
		display: flex;
		align-items: center;
		gap: 7px;
		color: var(--fg-dim);
		font-size: 0.73rem;
		min-height: 20px;
	}
	@media (max-width: 850px) {
		.request-form {
			grid-template-columns: minmax(210px, 250px) minmax(0, 1fr);
		}
		.settings-rail {
			padding: 22px 16px;
		}
		.toolbar button {
			padding: 6px 8px;
			font-size: 0.7rem;
		}
	}
	@media (max-width: 680px) {
		.request-form {
			display: flex;
			flex-direction: column;
		}
		.settings-rail {
			width: 100%;
			border-right: 0;
			border-bottom: 1px solid var(--border);
		}
		.rail-heading {
			display: none;
		}
		.settings-toggle {
			display: flex;
			justify-content: space-between;
			align-items: center;
			width: 100%;
			padding: 0;
			border: 0;
			background: none;
			font-weight: 650;
		}
		.settings-toggle span {
			color: var(--fg-dim);
			font-size: 0.67rem;
			font-weight: 400;
		}
		.rail-content.mobile-collapsed {
			display: none;
		}
		.composer {
			width: 100%;
			padding: 20px 16px;
		}
		.result-area {
			width: 100%;
			padding: 0 16px 24px;
		}
		.composer-heading {
			flex-wrap: wrap;
		}
		.library .result-area {
			padding: 22px 16px;
		}
	}
</style>
