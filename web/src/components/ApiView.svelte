<script lang="ts">
	import { BookOpen, Copy, ExternalLink } from '@lucide/svelte';
	import { toast } from '../lib/state.svelte.js';
	const request = JSON.stringify(
		{
			style: 'English, warm piano pop, expressive female voice',
			lyrics: '[Verse]\nA little light comes through the window',
			duration: 30,
			steps: 8
		},
		null,
		2
	);
	const command = `curl -X POST '${location.origin}/synth' \\\n  -H 'Content-Type: application/json' \\\n  --data '${request}'`;
	const music = JSON.stringify(
		{
			model: 'yue2',
			lyrics: '[Verse]\nA little light comes through the window',
			style: 'English, warm piano pop, expressive female voice',
			duration: 30,
			steps: 8,
			response_format: 'opus'
		},
		null,
		2
	);
	const musicCommand = `curl '${location.origin}/v1/audio/music' -H 'Content-Type: application/json' --data '${music}' --output song.opus`;
	const mcpConfig = JSON.stringify(
		{ mcpServers: { yue2: { type: 'http', url: `${location.origin}/mcp` } } },
		null,
		2
	);
	const python = [
		'from openai import OpenAI',
		'',
		`client = OpenAI(base_url="${location.origin}/v1", api_key="local")`,
		'with client.audio.speech.with_streaming_response.create(',
		'    model="yue2",',
		'    input="A little light comes through the window",',
		'    instructions="English piano pop, expressive female singing",',
		'    voice="auto",',
		'    response_format="flac",',
		'    extra_body={"duration": 30, "steps": 8},',
		') as response:',
		'    response.stream_to_file("song.flac")'
	].join('\n');
	async function copy(text = command) {
		try {
			await navigator.clipboard.writeText(text);
			toast('Request copied', 2500, true);
		} catch {
			toast('Clipboard unavailable. Select and copy the request below.');
		}
	}
</script>

<div class="api-view">
	<div class="page-heading">
		<div>
			<h2 class="section-heading"><BookOpen size={20} /> Local music API</h2>
			<p>Use the same generation engine from your own tools.</p>
		</div>
		<a
			class="secondary-button"
			href="https://github.com/hangry-labs/yue2/blob/master/docs/ARCHITECTURE.md"
			target="_blank"
			rel="noreferrer"><ExternalLink size={14} /> Full reference</a
		>
	</div>
	<div class="api-grid">
		<section class="surface">
			<h3>Music generation</h3>
			<p class="field-help">
				POST /v1/audio/music returns one audio file directly. Music stays at 48 kHz stereo. Requests
				share the same serial queue as the studio.
			</p>
			<div class="code-heading">
				<span>Bash / curl</span><button
					class="secondary-button"
					type="button"
					onclick={() => copy(musicCommand)}><Copy size={14} /> Copy</button
				>
			</div>
			<pre><code>{musicCommand}</code></pre>
			<p class="field-help">
				Use FLAC or WAV for lossless exports. MP3 remains the default when a format is omitted.
			</p>
		</section>
		<section class="surface">
			<h3>OpenAI-compatible clients</h3>
			<p class="field-help">
				POST /v1/audio/speech uses the same music engine. Input is lyrics; instructions describes
				the music. Voice aliases are approximate vocal hints.
			</p>
			<pre><code>{python}</code></pre>
			<p class="field-help">
				The complete song is generated before delivery. The streaming-response helper downloads the
				result; live generation and speech SSE events are unavailable. Explicit PCM export uses 24
				kHz mono PCM16LE.
			</p>
		</section>
	</div>
	<section class="surface routes">
		<h3>API discovery and access</h3>
		<p class="field-help">
			<a href="/openapi.json" target="_blank" rel="noreferrer">Download OpenAPI schema</a>. GET
			/v1/models lists YuE2. The native asynchronous routes below retain scores, replay data,
			latents and batch output.
		</p>
		<p class="field-help">
			Set YUE2_API_KEY to require a local Bearer key on /v1 and /mcp routes. Add an Authorization
			header to curl or replace local in the Python example with that key. Studio/native routes
			retain their existing local access policy.
		</p>
	</section>
	<div class="api-grid">
		<section class="surface">
			<h3>Music tools for agents</h3>
			<p class="field-help">
				Connect an MCP client over Streamable HTTP. Retrieve skill first, write or prepare a full
				song, then generate and poll for a download link. The same serial queue serves agents and
				Studio.
			</p>
			<div class="code-heading">
				<span>MCP connection</span><button
					class="secondary-button"
					type="button"
					onclick={() => copy(mcpConfig)}><Copy size={14} /> Copy</button
				>
			</div>
			<pre><code>{mcpConfig}</code></pre>
			<p class="field-help">
				Client configuration varies. If a local API key is configured, add its Bearer Authorization
				header to the connection.
			</p>
		</section>
		<section class="surface">
			<h3>Read, create, collect</h3>
			<ol>
				<li>
					<code>skill</code><span>Read the guide and keep its guide token.</span>
				</li>
				<li>
					<code>generate_song</code><span
						>Supply full-song lyrics and musical style; optionally duration, BPM hint and Opus or
						FLAC. Defaults to 150 seconds.</span
					>
				</li>
				<li>
					<code>get_song</code><span
						>Poll every two seconds. Download or share the completed HTTP link.</span
					>
				</li>
				<li>
					<code>cancel_song</code><span>Cancel a queued or generating song using its handle.</span>
				</li>
			</ol>
			<p class="field-help">
				Links expire one hour after completion. Audio stays 48 kHz stereo and is never embedded in
				tool responses. Agents have no runtime settings or quality controls.
			</p>
			<p class="field-help">
				<a href="/skills/songwriting/SKILL.md" target="_blank" rel="noreferrer">Read the skill</a>
				·
				<a
					href="https://github.com/hangry-labs/yue2/blob/master/docs/MCP.md"
					target="_blank"
					rel="noreferrer">MCP reference</a
				>
			</p>
		</section>
	</div>
	<div class="api-grid">
		<section class="surface">
			<h3>Generate a song</h3>
			<p class="field-help">
				Submit a request, poll its job, then download the result. Generation stays on the machine
				running this container.
			</p>
			<div class="code-heading">
				<span>Bash / curl</span><button
					class="secondary-button"
					type="button"
					onclick={() => copy()}><Copy size={14} /> Copy</button
				>
			</div>
			<pre><code>{command}</code></pre>
			<p class="field-help">
				The example explicitly uses 8 flow-matching steps. Omitted settings use the server defaults.
			</p>
		</section>
		<section class="surface">
			<h3>Follow the job</h3>
			<ol>
				<li>
					<code>POST /synth</code><span>Returns <code>{'{"id":"…"}'}</code> immediately.</span>
				</li>
				<li>
					<code>GET /job?id=ID</code><span
						>Poll until the status is <code>done</code>. Handle <code>failed</code> and
						<code>cancelled</code>.</span
					>
				</li>
				<li>
					<code>GET /job?id=ID&amp;result=1</code><span
						>Returns multipart audio, replay JSON and VAE latents.</span
					>
				</li>
			</ol>
			<p class="field-help">
				Cancel with <code>POST /job?id=ID&amp;cancel=1</code>. Completed results survive restarts on
				the output volume until expiry (24 hours by default). Active and queued work does not
				resume.
			</p>
		</section>
	</div>
	<section class="surface routes">
		<h3>Discovery and tools</h3>
		<dl>
			<dt><code>GET /health</code></dt>
			<dd>Service liveness, queue capacity and result storage usage</dd>
			<dt><code>GET /status</code><br /><code>GET /system/queue</code></dt>
			<dd>Queue counts and limits, active work, retry guidance and volume usage</dd>
			<dt><code>GET /props</code></dt>
			<dd>Configured models, capabilities, output formats and request defaults</dd>
			<dt><code>GET /logs</code></dt>
			<dd>Live server logs via server-sent events</dd>
			<dt><code>GET /system/gpu</code></dt>
			<dd>Demand-driven NVIDIA telemetry</dd>
			<dt><code>POST /vae</code></dt>
			<dd>Audio and latent encoding / decoding</dd>
			<dt><code>POST /transcribe</code><br /><code>POST /tokenize</code></dt>
			<dd>Optional models required; check System for availability</dd>
		</dl>
		<p class="field-help">
			This is YuE2's native asynchronous API. Keep the published port on localhost unless you
			intentionally configure remote access.
		</p>
	</section>
</div>

<style>
	.api-view {
		max-width: 1400px;
		margin: 0 auto;
		padding: 30px;
	}
	.page-heading {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 15px;
		margin-bottom: 23px;
	}
	.page-heading p {
		color: var(--fg-dim);
		font-size: 0.78rem;
	}
	.api-grid {
		display: grid;
		grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr);
		gap: 20px;
		margin-bottom: 20px;
	}
	.api-grid .surface {
		margin: 0;
	}
	.routes {
		margin-bottom: 20px;
	}
	.code-heading {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-top: 18px;
		color: var(--fg-dim);
		font-size: 0.7rem;
	}
	pre {
		padding: 14px;
		margin: 10px 0;
		background: var(--bg);
		border: 1px solid var(--line-soft);
		border-radius: 5px;
		overflow-x: auto;
		font-size: 0.72rem;
		line-height: 1.7;
	}
	code {
		overflow-wrap: anywhere;
		font-size: 0.73rem;
	}
	ol {
		padding: 0 0 0 19px;
		margin: 20px 0;
	}
	li {
		padding: 0 0 21px 7px;
		font-size: 0.8rem;
	}
	li > code {
		color: var(--accent-hover);
	}
	li span {
		display: block;
		margin-top: 8px;
		color: var(--fg-dim);
		line-height: 1.6;
		font-size: 0.75rem;
	}
	dl {
		display: grid;
		grid-template-columns: minmax(140px, 0.7fr) 1.3fr;
		gap: 17px;
		margin: 22px 0;
	}
	dt,
	dd {
		margin: 0;
		font-size: 0.76rem;
		line-height: 1.6;
	}
	dd {
		color: var(--fg-dim);
	}
	@media (max-width: 850px) {
		.api-grid {
			grid-template-columns: 1fr;
		}
	}
	@media (max-width: 540px) {
		.api-view {
			padding: 22px 16px;
		}
		.page-heading {
			flex-wrap: wrap;
		}
		dl {
			grid-template-columns: 1fr;
			gap: 8px;
		}
		dd {
			margin-bottom: 10px;
		}
	}
</style>
