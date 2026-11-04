# Music tools for agents

Connect an MCP client to **`http://localhost:8087/mcp`** using Streamable HTTP.
It runs inside Studio's container and shares its single generation queue.
No extra service, model download or parallel GPU worker is needed.

For clients with a remote HTTP server configuration:

```json
{
  "mcpServers": {
    "yue2": {
      "type": "http",
      "url": "http://localhost:8087/mcp"
    }
  }
}
```

Client configuration names vary; select **Streamable HTTP**, not the older
HTTP+SSE transport. If the operator sets `YUE2_API_KEY`, configure
`Authorization: Bearer YOUR_KEY` on the MCP connection. This uses the same key
as the [music API](API.md); it is not OpenAI authentication or OAuth.

## Four tools

| Tool | Input | Result |
| --- | --- | --- |
| `skill` | None | Current Markdown skill, version, one-hour `guide_token` |
| `generate_song` | Guide token, lyrics, direction; optional duration, tempo, format | Opaque job handle, queued status, poll interval |
| `get_song` | `job_id` | Progress or an HTTP download link and audio metadata |
| `cancel_song` | `job_id` | Cancellation for that job only; completed files remain available |

All tool descriptions direct agents to retrieve **`skill` first if they have
not already read it in the current conversation**. Agents then copy its token into
generation calls. The server checks retrieval, not whether an agent understood
the text. Reference copies are the MCP resource `yue2://skills/songwriting` and
[`GET /skills/songwriting/SKILL.md`](http://localhost:8087/skills/songwriting/SKILL.md).
Only `skill` issues the acknowledgement token.
The maintained source is [SKILL.md](https://github.com/hangry-labs/yue2/blob/master/src/agent/skills/songwriting/SKILL.md).

The guide teaches agents to write original lyrics from an idea, develop partial
lyrics, or arrange supplied words with section labels. It covers hooks, singable
phrasing, rhyme and pacing across a complete two-to-four-minute song. It explains
instrument and genre possibilities, uses `direction` for musical style and
lyric section labels for song form, and covers
returning a real completed link. A lyrics-only request should not trigger audio
generation. Prompting advice remains guidance rather than a fidelity guarantee.

Example `generate_song` arguments, after reading the guide:

```json
{
  "guide_token": "ACTUAL_TOKEN_RETURNED_BY_SKILL",
  "lyrics": "[Verse 1]\nNeon on the handlebars\nWe ride beneath electric stars\nBoots are dusty, wheels are bright\nWe bring the country to the night\n[Pre-Chorus]\nHear the city call our names\nWatch the sparks become a flame\n[Chorus]\nRide on, ride on! (hey!)\nWe will find another way\nSing it loud and carry on\nWe keep rolling till the dawn\n[Verse 2]\nSteel strings ring above the street\nOld-time hearts and future beats\nEvery corner, every bend\nBrings us closer to a friend\n[Pre-Chorus]\nHear the city call our names\nWatch the sparks become a flame\n[Chorus]\nRide on, ride on! (hey!)\nWe will find another way\nSing it loud and carry on\nWe keep rolling till the dawn\n[Bridge]\nWhen the towers fade to gold\nWe have stories to be told\nTake the long road, take my hand\nThere is room for us to land\n[Final Chorus]\nRide on, ride on! (hey!)\nWe will find another way\nSing it loud and carry on\nWe keep rolling till the dawn",
  "direction": "country pop, cyberpunk pop, futuristic, upbeat, male vocals, harmonies, acoustic guitar strumming, electric guitar twang, pedal steel, synth leads, punchy drums, sidechained bass, glossy modern production, neon atmosphere",
  "tempo_bpm": 112,
  "format": "opus"
}
```

Only these arguments are accepted. Duration is a **10–360-second ceiling**
(MCP default **300 seconds / five minutes**), not a target. Normally omit
`duration_seconds`; override it only for an explicit user duration constraint or
range. Do not write extra material to fill five minutes. A smaller ceiling may
truncate a song; this control cannot enforce an exact length or minimum.
Raising it alone does not extend a short song: lyric length, phrasing,
written-out repetitions, tempo and arrangement
affect the actual length; short lyrics can still yield repetitions or extended
instrumental passages. For a longer vocal song, provide enough lyrics and
sections to support it. Exact length is not guaranteed. Tempo is an optional
**30–300 BPM prompt hint**, not a timing guarantee or playback-speed adjustment.
Lyrics are passed verbatim; an empty
string allows an instrumental with suitable direction. New compositions use
fresh random seeds, the normal eight-step default and no inherited score.
Format is `opus` (compact default) or `flac` (lossless), both **48 kHz stereo**.
There are no model, voice-cloning, adapter, seed, sampling, quality, server
settings or model-residency tools. Unknown arguments are rejected.

Generation returns immediately. Wait for the returned `poll_after_seconds` before
the first `get_song` call and between later checks. Responses recommend
**30 seconds** to avoid unnecessary API calls. Three polls are not a timeout:
long songs and queued work can need more checks. Keep the existing handle and
continue polling pending work instead of failing or resubmitting it.
Use the returned handle. States are `queued`, `generating`, `complete`, `failed` and
`cancelled`. A disconnect leaves the song running; cancel explicitly if needed.
Cancellation is best effort if a song is already finishing. Completed status
includes `url`, `expires_at`, `ttl_seconds: 3600`, format, MIME type, duration,
size, sample rate and channel count. **No audio bytes or base64 are returned
through MCP.** Save the handle if the agent connection closes.

## One-hour downloads and persistence

Each download URL expires **one hour after its export completes**, independently
of queue time or the guide token. Download or share that URL directly. It works
without an Authorization header: the unpredictable 256-bit URL is the download
capability. Anyone holding it can fetch the song until expiry. GET, HEAD and
byte ranges are supported; responses use `Cache-Control: no-store`. Expired,
missing and invalid capabilities return 404. This controls server access;
it cannot revoke copies someone has already downloaded.

Only the selected export is stored, under `/output/agent-artifacts` in Docker.
Mount `/output` to keep completed links across container replacement:

```bash
docker run -d --name yue2 --gpus all \
  -p 127.0.0.1:8087:8087 \
  --mount "type=bind,source=$(pwd)/data/models,target=/models,readonly" \
  --mount type=volume,source=yue2-output,target=/output \
  hangrylabs/yue2:latest
```

The image runs as UID 10001; a custom bind mount must be writable by that user.
`task start` uses ignored `data/results/studio/` for persistent output. On Linux,
prepare that bind directory for UID 10001 before starting. Native/Studio results
use disk-backed server result storage; the browser library remains separate.
See [queue limits and storage](QUEUE.md). In-flight jobs and guide tokens are
process-local and disappear on restart; completed metadata and capability URLs
survive in persisted storage, with their original expiry.

Expired owned files are swept on startup, on submissions and every 30 seconds.
Every download checks expiry even before the sweep. Storage is bounded to 128
files / 2 GiB, with a 512 MiB per-file limit. Unexpired exports are never evicted
to make room; a full store fails the new export. Up to eight MCP songs may be
queued/generating; they still run serially. All compute routes also share the
configurable global eight-job limit. When full, tools return `isError: true`,
`structuredContent.code: queue_full` and `retry_after_seconds: 5`, with a
`Retry-After: 5` header. Wait with exponential backoff and jitter before retrying
a refused submission; poll accepted handles instead of resubmitting.

For clients on another machine or a forwarded port, set the operator environment
variable **`YUE2_MCP_PUBLIC_URL`** to their reachable HTTP(S) origin, for example
`https://music.example.org`. The default is `http://localhost:8087`. Links use
this configured origin, never an untrusted Host or forwarded header. Paths,
queries, fragments and embedded credentials are rejected. Configure a proxy to
forward `/mcp`, `/artifacts/` and `/skills/` with the configured Host/Origin.
Set the API key when enabling intentional remote access. This MCP policy does
not secure older native/Studio routes; keep those within their local scope.

`YUE2_MCP_OUTPUT_DIR` optionally selects an operator-owned export directory;
the default `agent-artifacts` is relative to the server working directory
(`/output` in Docker). Neither environment variable is an agent argument.
Preserve the output directory and public origin to keep URLs usable.

## Transport and development

The native adapter implements JSON-response Streamable HTTP: modern
**2026-07-28** requests and legacy **2025-11-25 / 2025-06-18** initialization.
Modern clients supply per-request metadata and matching protocol/method/name
headers. It has no sessions, subscriptions, server callbacks or SSE stream;
GET and DELETE `/mcp` return 405. The tool catalog is invariant. Known legacy
notifications receive 202; song cancellation uses its explicit tool.
Host and Origin are checked on the MCP transport. Loopback, Docker's local host
alias and the configured public origin are allowed; arbitrary browser origins
are rejected. No wildcard CORS is enabled.

`task check:cpu` exercises the native transport with a model-free fixture:
restricted arguments, guide gating, both protocol eras, exact expiry boundary,
persistence, capability lookups, downloads and ranges. The fixture is excluded
from the runtime image. The explicit
[official SDK client check](https://github.com/hangry-labs/yue2/blob/master/tests/clients/mcp_client.py) generates one real
song and downloads its link; it is a manual GPU check, not routine CI.

The separate [songwriting agent check](https://github.com/hangry-labs/yue2/blob/master/tests/agents/README.md)
tests an actual language model using full-song briefs. By default it retrieves
the real skill and validates proposed calls against the live tool schema,
stopping before generation is submitted. It records the model's choices without
repairing its arguments. Explicit `--generate-audio` enables the optional
end-to-end generation workflow. Audio or ASR quality is not an acceptance check.

The transport follows the official
[MCP specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http).
Temporary links follow the pattern used in Hangry Labs' Faster Qwen TTS;
audio inference remains entirely local here.
