# Docker runtime

Build and operate the local image with Task:

```text
task init
task start
task status
```

Open http://localhost:8087. task init downloads/verifies external models and
builds the image; task start preserves upstream inference defaults.

## Registry images

The publication workflow targets `hangrylabs/yue2` on Docker Hub and
`ghcr.io/hangry-labs/yue2` on GHCR. `master` publishes `latest` to both; stable
Git tags publish matching `vX.Y.Z` tags. The first `latest` publication succeeded
on both registries. The GGML dependency release is separate from this runnable
application image. For model downloads and Bash/PowerShell quick starts, see
the [README](../README.md#quick-start). The [Docker Hub overview](dockerhub.md)
is maintained separately for the registry page.

With the two external model files downloaded, PowerShell:

```powershell
docker run -d --name yue2 --gpus all -p 127.0.0.1:8087:8087 --mount "type=bind,source=$($PWD.Path)\models,target=/models,readonly" hangrylabs/yue2:latest
```

For GHCR, replace the image with `ghcr.io/hangry-labs/yue2:latest`. In Bash, use
`--mount "type=bind,source=$(pwd)/models,target=/models,readonly"`. The models are
not included or downloaded by the server. `task models` prepares them. The
rolling `latest` image follows development; stable release commands should use
the version tag and the top-level OCI digest verified on both registries.

See [publication and visibility](RELEASING.md) for the first GHCR package's public
access setting and the workflow's post-upload digest checks.

## Manual build and run

For the development RTX 5070 Ti:

```text
docker build --build-arg CUDA_ARCHITECTURES=120a-real --build-arg BUILD_JOBS=4 -t yue2:dev .
```

PowerShell, from the checkout with both model files present:

```powershell
docker run -d --name yue2-dev --gpus all -p 127.0.0.1:8087:8087 --mount "type=bind,source=$($PWD.Path)\models,target=/models,readonly" yue2:dev
```

For Bash, use `--mount "type=bind,source=$(pwd)/models,target=/models,readonly"`.
The locally built tag is yue2:dev. Models are not baked in and are not
automatically downloaded by the server; task models handles that.

GGML/CUDA compilation has its own reusable stage, independent of application,
UI and revision changes. `task deps:build` can prepare a portable dependency
artifact for CI. Normal Task/CI builds download and verify the pinned public
release archive; direct Docker builds use the source fallback unless a named
context or artifact image is supplied. See [build dependencies](BUILDING.md).
The artifact contains code libraries, never model weights.

## Weight-free packaging

The runtime build must pass `scripts/check_no_weights.py` before Docker can
produce the final image. This applies to `task build`, direct Docker builds
and the CI publication workflow. The checker inspects the assembled image
filesystem, including the base image, for common weight extensions (GGUF,
SafeTensors, PyTorch checkpoints, ONNX, `.bin` and others) and GGUF/GGML file
headers even when a file has been renamed. A match or an unreadable file fails
the build and identifies the offending path. Python stays in the checking stage.

The Docker context also excludes those extensions everywhere, in addition to
the entire `models/`, `checkpoints/` and `adapters/` directories. Model downloads
and read-only runtime mounts are unaffected. These checks catch common accidental
inclusions; they do not identify every possible encoding or inspect archives.

## Runtime settings

Default model filenames are /models/YuE2-3B-Q8_0.gguf and
/models/YuE2-Vae-F32.gguf. Default server port is 8087, backend selection is
automatic, context is 24576 and batch limit is one. Models are released under
the upstream strict eviction policy. No keep-loaded or reduced-context override
is applied by task start.

Container arguments replace the default server arguments. Include required
`--model` and `--vae` arguments and the network binding when supplying custom
options. `--max-seq` can reduce VRAM but can reject long requests whose prompt
plus token budget exceeds it. `--keep-loaded` retains models and requires
additional VRAM.

Choose a single GPU with Docker's `--gpus device=0` instead of `--gpus all`.
The server selects its compute backend automatically; `--device CUDA0` refers
to the first GPU visible inside the container, after Docker's GPU filtering.
The `YUE2_*` values in `.env.example` configure host-side Task commands, not
the server's container environment.

For optional adapters, create a host `adapters/` directory alongside `models/`.
Use this command when creating the container. PowerShell:

```powershell
docker run -d --name yue2 --restart unless-stopped --gpus all -p 127.0.0.1:8087:8087 --mount "type=bind,source=$($PWD.Path)\models,target=/models,readonly" --mount "type=bind,source=$($PWD.Path)\adapters,target=/adapters,readonly" hangrylabs/yue2:latest
```

In Bash use `source=$(pwd)/models` and `source=$(pwd)/adapters` in the respective
mounts. The default image command already sets `--adapters /adapters`. Adapter
files remain external to the image.

The runtime uses non-root UID 10001. Host port is bound to localhost by the task.
For a CLI run, override --entrypoint with yue-synth or another native executable
and mount a writable output directory at /output. Linux output directories must
be writable by the container user; the baseline runner selects the host UID.

## Persistence and health

| Storage | Behavior |
| --- | --- |
| Host models/ mounted at /models | Model files survive container replacement |
| Host adapters/ mounted at /adapters by task start | Optional LoRA files |
| Browser IndexedDB/localStorage | Songs, artifacts and form state |
| Server memory | Jobs/results are cleared on restart |
| Host results/ | Baseline audio, requests and logs |

The health check calls /health. It proves liveness, not a successful generation.
task test1 performs a full model-dependent generation. See
[BENCHMARKS.md](BENCHMARKS.md) for measured results.

System in the browser studio shows read-only NVIDIA telemetry from
`GET /system/gpu`. The native server uses NVML from the host driver, loaded
on demand, with no shell commands or background sampler. Requests share a
one-second cache and at most ten minutes of sampled history. The browser polls
only while System and the document are visible; missing sensors remain null.
The endpoint uses `Cache-Control: no-store`. CPU-only builds or containers
without the NVIDIA monitoring library return an empty GPU list and an
unavailable message. GPU visibility can include other workloads on the device.

`GET /props` now includes `capabilities.transcribe`, `capabilities.tokenize`
and `capabilities.vae`, so optional actions can be disabled before submission.
Configured model paths indicate configuration rather than current VRAM residency.
Run `task test:api` for read-only checks against the running local server.

The image is weight-free but the general CUDA runtime base is still sizeable.
Runtime library trimming remains future packaging work; there is only one image
variant. CUDA/base-image and dependency terms remain applicable.
