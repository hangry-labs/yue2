# Hangry Labs YuE2

Development version **v0.1.0-snapshot**.

Local song generation in a Docker container, with a browser UI and HTTP API.
Give YuE2 style tags and lyrics; it produces stereo 48 kHz audio together with
an editable ABC score, semantic codes and acoustic latents.

This fork keeps the C++17/GGML engine and standalone UI from
[yue2.cpp](https://github.com/ServeurpersoCom/yue2.cpp), and organizes development,
packaging and testing around Docker and Task.

## Quick start from source

Install Docker with NVIDIA GPU support, Python 3.11+ and
[Task](https://taskfile.dev). No model weights are included in the image.

```text
git clone https://github.com/hangry-labs/yue2.git
cd yue2
task doctor
task init
task start
```

Open **http://localhost:8087**. Enter style tags and lyrics, then Generate.
The local CUDA image has been tested on an RTX 5070 Ti with 16 GB VRAM.
The first build compiles CUDA kernels and can take several minutes.

`task init` verifies/downloads the two pinned GGUF files into `models/` and
builds `yue2:dev`. Downloads total approximately 4.34 GB. Cached models are
verified and reused. Models remain outside the image and are mounted read-only.

There is one image variant. No registry image has been published yet; the
commands above build locally. See [Docker details](docs/DOCKER.md).

## What you get

- Style-and-lyrics song generation, with full score, melody-only and no-score modes.
- Editable ABC scores and semantic-token replay.
- MP3 or WAV output, browser playback and track downloads.
- Continuation from a selected section of source semantic tokens.
- LoRA adapters loaded from the local adapters directory.
- VAE audio/latent encoding and decoding.
- Optional recording transcription and audio tokenization when their additional
  models and server arguments are supplied.

The server processes compute jobs on one worker with progress logs and
cancellation. The native API is an asynchronous music API, not an
OpenAI-compatible API. Optional transcription models are not downloaded by
`task init`; see [models](docs/MODELS.md).

## Data and defaults

| Location | Contents |
| --- | --- |
| `models/` | Persistent, external GGUF files and pinned download manifest |
| `adapters/` | Optional LoRA files and folders |
| Browser IndexedDB | Song cards, audio and latent artifacts |
| Browser localStorage | Form settings and pending-job state |
| `results/test1/` | Local baseline outputs, requests, logs and timings |

Server jobs and results are in memory and disappear on restart. Export songs
you want to keep; mounting models does not back up browser storage.

Normal startup preserves upstream inference defaults: **24,576-token context**,
automatic backend selection and strict model eviction between stages.
Reducing `--max-seq` saves VRAM but can reject longer requests. The repeatable
baseline explicitly uses **8 flow-matching steps**; the upstream server request
default remains 32. Existing browser form values still control requests.

## Development commands

```text
task build
task start
task status
task logs
task stop
task validate
task test1
```

Run `task --list` for all commands. Copy `.env.example` to `.env` for local
settings, or override a Task variable: `task start PORT=8088`,
`task build CUDA_ARCHITECTURES=120a-real`, or `task test1 SEED=123`.
Use `PYTHON=python3` where that is your Python executable.

`task test1` runs the prompt in [tests/fixtures/test1.txt](tests/fixtures/test1.txt)
through a temporary GPU container with fixed seeds and 8 steps. It saves audio,
score, tokens, latents, replay settings and a JSON timing summary.
The initial baseline produced **270.8 seconds of audio in 85.1 seconds of
pipeline time**. See [benchmark methodology](docs/BENCHMARKS.md).

## API

Submit JSON to `POST /synth`, poll `GET /job?id=...`, and fetch the result with
`GET /job?id=...&result=1`. Each generation result contains replay JSON, audio
and latents. `POST /job?id=...&cancel=1` requests cancellation.

Discovery/liveness routes are `GET /props` and `GET /health`; `GET /logs`
streams logs. `/health` is liveness, not a completed inference test.
See the [technical and API reference](docs/ARCHITECTURE.md).

## Repository guide

| Directory | Purpose |
| --- | --- |
| `src/` | Native inference engine; `src/cli/` contains executable entry points |
| `web/` | Svelte 5/TypeScript UI and embedded asset |
| `scripts/` | Cross-platform Task helpers and advanced model conversion tools |
| `cmake/` | Version and asset-embedding build helpers |
| `benchmarks/` | Repeatable generation runner |
| `tests/unit/` | CPU-only tooling and lifecycle tests |
| `tests/fixtures/` | Baseline prompts |
| `tests/parity/` | Optional upstream numerical/reference harnesses and historical logs |
| `vendor/` | Third-party code, including the pinned GGML source snapshot |

GGML is ordinary vendored source at the exact tested upstream revision.
No recursive clone, nested Git checkout or update wrapper is required.
Its license, source commit and file hashes are preserved. See
[dependency policy](docs/DEVELOPMENT.md#vendored-dependencies).

## Documentation

- [Development and repository layout](docs/DEVELOPMENT.md)
- [Docker runtime](docs/DOCKER.md)
- [Models and conversion](docs/MODELS.md)
- [Baseline generation](docs/BENCHMARKS.md)
- [CI and releases](docs/RELEASING.md)
- [Architecture, API and CLI reference](docs/ARCHITECTURE.md)

## Privacy, responsible use and licenses

Generation runs on your machine. The local setup binds the published port to
localhost. Use recordings, lyrics and other material you are entitled to use.
Browser pairing and external application integrations are not implemented.

This project is based on YuE2 by [MAP](https://huggingface.co/m-a-p/YuE2-3B),
with the native engine from yue2.cpp and its patched GGML fork.
Application source is MIT; model weights carry separate **CC BY-NC 4.0**
terms. Keeping weights outside the image does not change those terms.
CUDA and other runtime dependencies retain their own licenses.
See [LICENSE](LICENSE), [third-party notices](THIRD_PARTY_NOTICES.md) and
[model provenance](docs/MODELS.md).
