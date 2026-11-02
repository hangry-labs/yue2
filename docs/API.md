# Music and OpenAI-compatible audio APIs

The studio, native jobs and both audio endpoints share port **8087** and one
FIFO compute worker. Requests never execute GPU inference in parallel. All
models and generated audio stay on the machine running the container.

Open [the local API guide](http://localhost:8087/docs) or download
`http://localhost:8087/openapi.json` for the OpenAPI 3.1 contract. The guide is
packaged in the image and works without a CDN.

For agents, connect to [`/mcp`](MCP.md). Its four tools require reading the
songwriting guide first, expose basic musical controls and return HTTP
download links valid for one hour after completion.

## Generate music

`POST /v1/audio/music` is our music extension. It returns one complete audio file:

```bash
curl http://localhost:8087/v1/audio/music \
  -H 'Content-Type: application/json' \
  --data '{"model":"yue2","lyrics":"[Verse]\nMorning light across the floor\nA little song outside the door","style":"English acoustic pop, warm female singing, gentle guitar","duration":30,"steps":8,"response_format":"flac"}' \
  --output song.flac
```

Use `lyrics` and `style`, or their compatibility equivalents `input` and
`instructions`. Lyrics are passed verbatim. If both `input` and `lyrics` are
provided, they must match. `instructions` supplements `style` when both exist.
An empty lyric string with instrumental direction is supported. Omitted model
selection resolves to YuE2; harmless unrelated fields are ignored.

`/v1/audio/music` is a local extension, not an official OpenAI endpoint. Existing
OpenAI SDKs use the speech adapter below rather than an `audio.music` resource.

## OpenAI clients

`POST /v1/audio/speech` accepts the same requests and returns the same audio.
It generates **songs**, including when the input is ordinary text. This service
does not provide spoken narration or OpenAI voice identities.

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8087/v1", api_key="local")
with client.audio.speech.with_streaming_response.create(
    model="yue2",
    input="[Verse]\nMorning light across the floor\nA little song outside the door",
    instructions="English acoustic pop, warm female singing, gentle guitar",
    voice="auto",
    response_format="flac",
    extra_body={"duration": 30, "steps": 8},
) as response:
    response.stream_to_file("song.flac")
```

```javascript
import OpenAI from "openai";
import { writeFile } from "node:fs/promises";

const client = new OpenAI({ baseURL: "http://localhost:8087/v1", apiKey: "local" });
const response = await client.audio.speech.create({
  model: "yue2",
  input: "Morning light across the floor. A little song outside the door.",
  instructions: "English acoustic pop, warm female singing, gentle guitar",
  voice: "auto",
  response_format: "opus",
  duration: 30,
  steps: 8,
});
await writeFile("song.opus", Buffer.from(await response.arrayBuffer()));
```

The JavaScript example is plain JavaScript; typed clients can pass music-only
fields through their SDK's extra-body mechanism or call the music endpoint.
The complete song is generated before response delivery. Streaming-response
helpers can download the completed file, but this is not live music generation.
`stream_format="audio"` works; speech SSE events and `stream=true` are rejected.

## Models and voices

`GET /v1/models` lists the actual local `yue2` model with its capabilities.
`GET /v1/models/{id}` also resolves `yue2-3b`, `tts-1`, `tts-1-hd` and
`gpt-4o-mini-tts`. These aliases all use local YuE2; no provider model or cloud
account is involved. Unknown models return 404.

`voice` defaults to `auto`, which adds no vocal hint. `default` behaves the same.
These hints supplement musical direction; they do not identify fixed singers:

| Values | Hint added to the musical direction |
| --- | --- |
| `female`, `nova`, `shimmer`, `coral` | Clear female lead vocals |
| `male`, `echo`, `onyx`, `cedar` | Clear male lead vocals |
| `alloy`, `ash`, `sage`, `marin` | Warm clear lead vocals |
| `ballad`, `fable`, `verse` | Expressive storytelling lead vocals |

Describe other vocal delivery in `style`/`instructions`. Custom voice objects,
unknown voice IDs and voice cloning are not supported by this adapter.

## Audio quality and controls

Normal exports retain **48 kHz stereo**. `response_format` accepts `mp3` (default),
`opus`, `aac`, `flac`, `wav`, `pcm`, plus `ogg`, `m4a`, `wav16`, `wav24`, `wav32`.
`wav` maps to `wav16`. `output_format` is accepted as an equivalent field; if
both format fields are supplied they must agree. See [encoding profiles](AUDIO.md).

Choose FLAC or WAV for lossless exports. `wav32` retains the raw floating-point
output without normalization. **Only explicit `pcm` export** converts to the
compatibility layout: 24 kHz, mono, signed 16-bit little-endian samples without
a header. It does not change normal exports or the model's output rate.

`speed` accepts 0.25–4.0, default 1. It changes the output tempo through
pitch-preserving FFmpeg processing after generation. It is separate from
inference speed and the musical BPM in your prompt. The duration ceiling applies
before this output adjustment.

Native settings such as `duration`, `steps`, seeds, CFG, sampling controls,
adapters, explicit ABC scores and replay/continuation tokens are supported.
Normal calls generate a fresh score and random seeds unless conditioning or
fixed seeds are explicitly supplied. Both audio endpoints return exactly one
track: `n`, `lm_batch_size` and `synth_batch_size` must be 1 when provided.

Responses contain the audio directly with the correct MIME type and extension,
plus `X-Request-ID`, `X-YuE2-Job-ID`, `X-Audio-Sample-Rate` and `X-Audio-Channels`.
Use `/synth` for asynchronous work, native batches, replay JSON and latents.
The existing [native API reference](ARCHITECTURE.md#endpoints) remains available.

## Authentication, errors and cancellation

Set `YUE2_API_KEY` to require `Authorization: Bearer YOUR_LOCAL_KEY` on `/v1`
and `/mcp` routes. SDK examples use a dummy `local` key because the SDK requires a key
argument; replace it with your configured key when authentication is enabled.
The key is local configuration, not an OpenAI account key.

For Docker, pass `--env YUE2_API_KEY` with the variable set in your shell. Local
Task commands also forward it from their environment/ignored `.env` without
printing its value, and preserve existing access settings across image updates.
An explicitly empty host value clears a previously configured key.

This authentication covers `/v1` and `/mcp`. Studio, native jobs, logs and System keep
their existing local access policy. The normal Docker binding remains localhost;
whole-service remote access requires its own access configuration.

`YUE2_API_TIMEOUT_SECONDS` defaults to 600 and includes time waiting in the queue.
The synchronous request cancels its own job on timeout or client disconnect.
Queued cancelled work is skipped before model loading; active work cancels at
the engine's existing checkpoints. Other jobs are unaffected. Native `/synth`
remains asynchronous. A failed connection after delivery starts cannot be changed
into a JSON error response.

V1 errors use `{"error":{"message":"…","type":"invalid_request_error","param":"…","code":"…"}}`.
Malformed/unsupported settings return 400, invalid keys 401, unknown models 404,
cancelled generation 409, generation failures 500 and the local deadline 504.
Schema and local guide routes are public. Unknown optional native model routes
remain unavailable; this change does not load transcription/tokenization models.

All compute routes share a configurable eight-job limit, including the active
job. Excess native/compatibility requests return **429** with `Retry-After: 5`;
compatibility errors retain the OpenAI envelope. Back off with jitter before
retrying refused submissions. Accepted jobs must be polled rather than submitted
again. An already-full native result store returns **507** before generation.

`GET /health`, `/status` and `/system/queue` report queue counts/capacity and
volume usage without exposing other callers' job handles or lyrics. Completed
native/API results are streamed from `/output/jobs`, survive restarts, and expire
after 24 hours by default. The browser library remains separate. See
[queue limits, persistence and load testing](QUEUE.md) for configuration and limits.

The compatibility reference is OpenAI's [speech endpoint](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create).
Music routes, native controls and extended formats are local capabilities.

## Validation

`task test:api` checks discovery, schema availability and rejected requests
without generating songs. `task check:cpu` tests native request translation,
error shapes, PCM layout and pitch-preserving speed limits without weights.
`tests/clients/python_client.py` and `tests/clients/javascript_client.cjs` are
explicit live SDK checks using a supplied native request JSON fixture and local
output paths. They generate audio; use a quiet local service and fixed seeds
when checking output against a reference.
