# Docker runtime

Build and operate the local image with Task:

```text
task init
task start
task status
```

Open http://localhost:8087. task init downloads/verifies external models and
builds the image; task start preserves upstream inference defaults.

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
No image is published yet. The local tag is yue2:dev. Models are not baked in
and are not automatically downloaded by the server; task models handles that.

GGML/CUDA compilation has its own reusable stage, independent of application,
UI and revision changes. `task deps:build` can prepare a portable dependency
artifact for CI. See [build dependencies](BUILDING.md) for registry reuse and
digest pinning. This artifact contains code libraries, never model weights.

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
--model and --vae arguments when supplying custom options. --max-seq can reduce
VRAM but can reject long requests whose prompt plus token budget exceeds it.
--keep-loaded retains models and requires additional VRAM.

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
