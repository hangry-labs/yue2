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
	async function copy() {
		try {
			await navigator.clipboard.writeText(command);
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
			<h3>Generate a song</h3>
			<p class="field-help">
				Submit a request, poll its job, then download the result. Generation stays on the machine
				running this container.
			</p>
			<div class="code-heading">
				<span>Bash / curl</span><button class="secondary-button" type="button" onclick={copy}
					><Copy size={14} /> Copy</button
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
				Cancel with <code>POST /job?id=ID&amp;cancel=1</code>. A container restart clears server
				jobs and results.
			</p>
		</section>
	</div>
	<section class="surface routes">
		<h3>Discovery and tools</h3>
		<dl>
			<dt><code>GET /health</code></dt>
			<dd>Service liveness</dd>
			<dt><code>GET /props</code></dt>
			<dd>Configured models, capabilities and request defaults</dd>
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
