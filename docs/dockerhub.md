<p align="center">
  <a href="https://github.com/hangry-labs/yue2">
    <img src="https://raw.githubusercontent.com/hangry-labs/yue2/master/web/src/assets/yue2_logo_horizontal.webp" alt="Hangry Labs YuE2 logo" width="900">
  </a>
</p>

# Hangry Labs YuE2

Local song generation from style tags and lyrics, with a browser studio,
asynchronous HTTP API and stereo 48 kHz MP3 or WAV output in one CUDA container.

Write lyrics, describe the music and generate on your own GPU. Keep the audio,
edit the ABC score or reuse the semantic tokens and acoustic latents.
**No model weights are included in this image.**

## Quick Start

Use Docker with NVIDIA GPU support and a driver compatible with the CUDA 12.9.1
runtime. The qualified machine is an **RTX 5070 Ti with 16 GB VRAM**; other GPU
configurations have not been qualified.

Create a local `data/models/` directory and download both files, preserving their names:

| Download | Size |
| --- | --- |
| [YuE2-3B-Q8_0.gguf](https://huggingface.co/Serveurperso/YuE2-GGUF/resolve/e630f2b8f6aedf8254c3186438633c1b5eeaf80a/YuE2-3B-Q8_0.gguf) | 3.81 GB |
| [YuE2-Vae-F32.gguf](https://huggingface.co/Serveurperso/YuE2-GGUF/resolve/e630f2b8f6aedf8254c3186438633c1b5eeaf80a/YuE2-Vae-F32.gguf) | 530 MB |

These links use the pinned publisher revision. Check file hashes against the
[model manifest](https://github.com/hangry-labs/yue2/blob/master/docker/models.json).
Alternatively, run `task models` from a project checkout to download and verify
them automatically. See the [model guide](https://github.com/hangry-labs/yue2/blob/master/docs/MODELS.md).

From the directory containing `data/models/`, run one of these commands using the
published, moving development tag `latest`:

**Bash:**

```bash
docker run -d --name yue2 --restart unless-stopped --gpus all -p 127.0.0.1:8087:8087 --mount "type=bind,source=$(pwd)/data/models,target=/models,readonly" hangrylabs/yue2:latest
```

**PowerShell:**

```powershell
docker run -d --name yue2 --restart unless-stopped --gpus all -p 127.0.0.1:8087:8087 --mount "type=bind,source=$($PWD.Path)\data\models,target=/models,readonly" hangrylabs/yue2:latest
```

Open **http://localhost:8087**, enter style tags and lyrics, then select
**Generate**. No host Python or compiler is needed to run the image. The
server does not download weights; generation can run offline once the image
and models are available.

## What You Get

- Style-and-lyrics generation with full score, melody-only and no-score modes.
- Stereo 48 kHz audio, browser playback and MP3/WAV downloads.
- Editable ABC scores, semantic replay and continuation from source tokens.
- Searchable browser library, favorites and reusable prompts.
- Local LoRA adapters and VAE audio/latent conversion.
- Asynchronous HTTP jobs, progress logs and cancellation.
- Model availability and NVIDIA GPU charts in System.

Recording transcription and audio tokenization are optional and require
additional models and startup arguments. Default downloads cover song generation.

## Browser UI

<p align="center">
  <a href="https://github.com/hangry-labs/yue2/blob/master/assets/screenshots/create-ui.webp">
    <img src="https://raw.githubusercontent.com/hangry-labs/yue2/master/assets/screenshots/create-ui.webp" alt="YuE2 Create workspace with musical direction, lyrics and generation settings" width="1200">
  </a>
</p>

The local studio uses the Hangry Labs charcoal-and-orange theme with four views:

| View | Workflow |
| --- | --- |
| Create | Enter musical direction and lyrics, edit a score, configure generation and play songs. |
| Library | Search saved songs, mark favorites, download artifacts and reuse prompts. |
| API | Inspect native request examples and the job workflow. |
| System | Inspect configured models, optional tools, GPU activity and logs. |

Switching views preserves the current composition and active generation. All
UI assets are served locally; no CDN is required.

**Generate song** composes from the current lyrics and musical direction, with
random seeds and 8 steps by default. Info buttons explain every setting. Saved
scores stay with songs in Library. **Edit prompt** starts a fresh take from saved
text; score reuse, replay and source continuation are explicit choices.

## Image Tags

There is one CUDA runtime image, with the same build published to both registries:

| Registry | Image |
| --- | --- |
| Docker Hub | `hangrylabs/yue2` |
| GHCR | `ghcr.io/hangry-labs/yue2` |

| Tag | Meaning |
| --- | --- |
| `latest` | Moving development build from `master` |
| `vX.Y.Z` | Matching stable application release, when published |

Replace the image in the quick start with `ghcr.io/hangry-labs/yue2:latest` to
use GHCR. A stable application release has not been recorded; the quick start
deliberately follows development. Stable commands will include verified OCI
index digests after release. The `ggml-deps-*` GitHub Release is a build-library
archive, not this runtime image.

## Persistent Data And Runtime Settings

| Storage | Behavior |
| --- | --- |
| Host `data/models/` at `/models`, read-only | Required models survive container replacement |
| Optional host `data/adapters/` at `/adapters`, read-only | Local LoRA adapters |
| Browser IndexedDB/localStorage | Saved songs, audio, latents and form settings |
| Server memory | Jobs/results disappear when the server restarts |

Download songs you want to keep. A model mount does not back up browser data;
a different browser or service address has a separate library. Server generation
does not automatically write songs into a host folder.

Defaults are a **24,576-token context**, automatic backend selection and strict
model eviction between stages. Requests default to **8 flow-matching steps**,
matching the recorded baseline and intentionally differing from upstream's 32. Saved browser settings control UI requests.

Choose a single GPU with Docker's `--gpus device=0` instead of `--gpus all`.
Server settings use command-line flags. Custom arguments replace the default
command, so include the model paths and network binding. `--max-seq` can reduce
VRAM at the cost of rejecting longer requests; `--keep-loaded` needs more VRAM.
See the [runtime guide](https://github.com/hangry-labs/yue2/blob/master/docs/DOCKER.md#runtime-settings).

The image runs as non-root UID 10001. The quick start binds port 8087 to
localhost; keep access restricted to trusted clients.

## API Example

The native music API shares port 8087 with the studio. **Bash with cURL:**

```bash
curl --fail-with-body http://localhost:8087/synth -H 'Content-Type: application/json' --data '{"style":"acoustic pop, warm vocals, gentle guitar","lyrics":"[verse]\nMorning light across the floor\nA little song outside the door","cot":"full","duration":30,"steps":8,"output_format":"mp3"}'
```

The response is `{"id":"..."}`. Replace `JOB_ID` with that value, poll until
the status is `done`, then fetch the result:

```bash
curl --fail-with-body "http://localhost:8087/job?id=JOB_ID"
curl --fail-with-body "http://localhost:8087/job?id=JOB_ID&result=1" --output song.multipart
```

The result is `multipart/mixed`: replay JSON, encoded audio and acoustic latents
for each track. `song.multipart` is the complete response, not an MP3. Parse
its parts or use the studio's individual downloads. Cancellation is
`POST /job?id=JOB_ID&cancel=1`.

`GET /props` describes configuration/capabilities, `GET /health` reports
liveness, `GET /logs` streams progress and `GET /system/gpu` reports GPU
telemetry. See the
[API reference](https://github.com/hangry-labs/yue2/blob/master/docs/ARCHITECTURE.md#endpoints).

## Benchmarks

The initial RTX 5070 Ti 16 GB run generated **270.8 seconds of audio in 85.1
seconds of pipeline time** and 90.5 seconds of total wall time, using Q8_0,
F32 VAE, full score generation, 8 steps and fixed seeds. Model hashing warmed
the filesystem before measurement. This is a single local result; see the
[benchmark methodology](https://github.com/hangry-labs/yue2/blob/master/docs/BENCHMARKS.md).

## Responsible Use And Privacy

Generation runs on your machine. Image/model downloads contact registries and
the model host. Use lyrics, scores and recordings you have rights to process;
obtain consent where recordings identify other people and avoid deceptive
impersonation. Review generated material before sharing it.

The application source is MIT. Model weights have separate **CC BY-NC 4.0**
terms, and keeping weights external does not change those terms. CUDA and
other dependencies retain their own licenses. Every runtime build checks the
assembled filesystem for common model-weight files and GGUF/GGML headers.
See [packaging safeguards](https://github.com/hangry-labs/yue2/blob/master/docs/DOCKER.md#weight-free-packaging)
and [third-party notices](https://github.com/hangry-labs/yue2/blob/master/THIRD_PARTY_NOTICES.md).

## Project Links And Attribution

- [Source and README](https://github.com/hangry-labs/yue2)
- [Docker runtime](https://github.com/hangry-labs/yue2/blob/master/docs/DOCKER.md)
- [Models and provenance](https://github.com/hangry-labs/yue2/blob/master/docs/MODELS.md)
- [Development](https://github.com/hangry-labs/yue2/blob/master/docs/DEVELOPMENT.md)
- [Publication rules](https://github.com/hangry-labs/yue2/blob/master/docs/RELEASING.md)
- [License](https://github.com/hangry-labs/yue2/blob/master/LICENSE)

[MAP's YuE2](https://huggingface.co/m-a-p/YuE2-3B) and
[YuE2-Vae](https://huggingface.co/m-a-p/YuE2-Vae) provide the models;
[yue2.cpp](https://github.com/ServeurpersoCom/yue2.cpp) provides the native
engine and original studio, using its patched GGML fork. Hangry Labs maintains
this fork's product UI, Docker packaging, workflows and baseline tooling.
