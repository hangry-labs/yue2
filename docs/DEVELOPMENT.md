# Development

The primary workflow uses Docker for C++/CUDA builds and Node UI checks.
Host dependencies are Docker/Buildx, NVIDIA GPU support, Python 3.11+ and Task.
Python helpers use the standard library; Python is not added to the inference image.

## Repository layout

| Directory | Purpose |
| --- | --- |
| `src/` | Native inference engine; `src/cli/` contains executable entry points |
| `web/` | Svelte 5/TypeScript studio and embedded UI asset |
| `scripts/` | Cross-platform Task helpers and advanced model conversion tools |
| `cmake/` | Build identity, asset embedding and reusable GGML package helpers |
| `docker/` | Pinned model-download manifest and compiled dependency configuration |
| `tests/benchmarks/` | Repeatable generation runner |
| `tests/unit/` | CPU-only tooling and lifecycle tests |
| `tests/integration/` | Read-only checks against a running server |
| `tests/fixtures/` | Baseline prompts |
| `tests/parity/` | Optional model-dependent upstream numerical harnesses and historical logs |
| `vendor/` | Third-party source, including the pinned GGML snapshot |
| `docs/` | [Documentation index](README.md), user/developer guides and the Docker Hub overview |
| `assets/` | [Artwork conversion notes](../assets/README.md) and documentation screenshots |

Model files and generated `data/results/` stay outside version control. GGML is
ordinary vendored source; no recursive clone or nested Git checkout is needed.

`src/` contains application code. `cmake/` and `docker/` describe how that code
is built and packaged, so they stay beside it. The root `CMakeLists.txt`,
`Dockerfile` and `Taskfile.yml` remain the build entry points; `.github/workflows/`
is GitHub's workflow location. `LICENSE`, `THIRD_PARTY_NOTICES.md`, `VERSION`
and the README remain easy to find at the repository root.

`build/` holds disposable compiler output, dependency downloads and publication
reports. User files belong in `data/`, separately from those build caches.
Both directories are ignored by Git and excluded from Docker's build context.
Product artwork belongs with the UI assets or documentation media, never in
the local model-data directories.

## Local data

| Host location | Purpose | Container location |
| --- | --- | --- |
| `data/models/` | Required and optional GGUF files | `/models`, read-only |
| `data/adapters/` | Optional LoRA adapters | `/adapters`, read-only |
| `data/checkpoints/` | Original checkpoints for advanced conversion/reference checks | Not mounted by normal startup |
| `data/results/` | Benchmark evidence and exported build-dependency archives | Per-run `/output` mount when needed |

Tasks create these directories when needed. The tracked download manifest is
[`docker/models.json`](../docker/models.json); model files are never tracked or
baked into the image. Browser songs/settings still live in browser storage,
and server jobs/results remain in memory.

For an existing checkout with root-level `models/`, `adapters/`, `checkpoints/`
or `results/`, finish active work before migrating:

```text
task stop
task data:migrate
task start
```

`task data:status` shows paths and pending moves. Migration renames local
directories without re-downloading files, refuses destination collisions and
live bind mounts, and never merges or overwrites existing data. If both old
and new locations contain files, reconcile them manually before retrying.
The downloader refuses legacy storage rather than downloading a second copy.
Existing external Docker deployments can keep their own host directories;
the in-container paths and server defaults have not changed.

## Task interface

| Command | Behavior |
| --- | --- |
| task doctor | Inspect Docker, Buildx and host GPU visibility |
| task models | Verify/download pinned external models |
| task data:status / data:migrate | Inspect storage or migrate an old checkout |
| task init | Models, then CUDA image build |
| task build | Rebuild current native engine and UI |
| task deps:build | Prebuild a reusable GGML artifact with all distribution CUDA targets |
| task deps:plan | Show the dependency fingerprint and pinned release artifact |
| task deps:prepare | Download and verify the public dependency archive |
| task deps:export | Export a local dependency archive and checksum for release upload |
| task start | Start the default server or replace an older project image |
| task stop / status / logs | Operate this project's container |
| task test | Tooling tests and GGML snapshot verification |
| task test:api | Read-only capabilities and GPU telemetry checks against the running server |
| task check:cpu | Compile all native targets and check executable loading in Docker |
| task web:check | Check UI types, request behavior and formatting in Node Docker |
| task web:build | Regenerate the embedded UI asset in Node Docker |
| task assets:build | Convert the original PNG artwork to WebP with host FFmpeg |
| task validate | Tooling, vendor, UI and CPU checks |
| task test1 | Full GPU generation baseline |
| task test1:prepare | Prepare the request without Docker inference |

Task configuration is in Taskfile.yml; implementation is in scripts/dev.py.
Defaults match .env.example. CLI variables override local settings.
Only the named project container is replaced. Start refuses replacement while a
known job is running and does not stop another project's container with that name.
Changing images restarts the process and clears its in-memory jobs/results.
Models and browser data persist.

Local builds reuse the pinned public release dependency when
targeting is automatic. Otherwise they detect host NVIDIA compute capability and
compile for that hardware. Set CUDA_ARCHITECTURES explicitly for a different build. Docker
builds have no GPU access, so do not pass the CMake value native to Docker builds.
The Dockerfile's broader architecture default is for distribution builds and
has not been qualified as a support matrix.

## Build stages and caching

Dockerfile stages:
- web: Node 24 checks and builds the current Svelte source.
- source: selects source files; excludes models and local state.
- cpu-checks: compiles all native targets and verifies startup without weights.
- cuda-toolchain: pinned CUDA 12.9.1 development base and build tools.
- ggml-deps-build / ggml-deps: isolated GGML compilation and portable dependency artifact.
- selected-ggml: verified release named context, source artifact or selected prebuilt image.
- build: C++17 app compilation linked against the verified GGML installation.
- weights-check: verifies the assembled image contains no common model-weight files.
- runtime: CUDA runtime, native executables, notices and embedded UI.

Compiled GGML libraries live in a normal Docker layer, separate from app source,
UI and revision inputs. This layer survives external cache export; BuildKit cache
mounts alone are not preserved by GitHub Actions caching. Local cache mounts also
retain app objects and compiler results. No cache or artifact contains model weights.
Normal Task/CI builds use the pinned public release archive as a named context.
See [build dependencies](BUILDING.md) for downloads, source builds and invalidation rules.

VERSION owns the application version. Task builds inject the Git revision;
CI injects the validated commit. The same version/revision is embedded in UI and
native binaries. Direct Docker builds without a SOURCE_REVISION argument show
an unknown revision, but retain the application version.

## Vendored dependencies

vendor/ggml is a source snapshot of ServeurpersoCom/ggml at
cc5df49a6b878db2b68b9a7b45976e279594627d. It replaces the former root submodule.
The runtime source is unchanged. It retains custom SNAKE/COL2IM_1D VAE support.

The snapshot excludes upstream CI/agent tooling and an empty .gitmodules file.
One example ignore file has packaging exceptions so its existing tracked source
is not lost when vendored. See vendor/ggml/UPSTREAM.md and the SHA-256 manifest
vendor/ggml.snapshot.json. Root .gitattributes preserves exact snapshot bytes.

Run task vendor:verify after updates. A dependency update is a reviewed source
change with refreshed provenance/hashes, CPU/CUDA validation and test1 generation;
there is no git-pull update task. Preserve all upstream notices.

## Native builds (advanced)

The Docker runtime is the supported development baseline. The original engine
also contains native CPU, CUDA, Vulkan, Metal and SYCL paths. They are not all
qualified as product distributions.

For CPU development with CMake/Ninja and a C++17 toolchain:

```text
cmake -S . -B build/native-cpu -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=OFF -DGGML_VULKAN=OFF
cmake --build build/native-cpu --parallel 4
python scripts/smoke_binaries.py build/native-cpu
```

Use a Visual Studio x64 developer environment on Windows. For native CUDA, use
a separate build/native-cuda directory with -DGGML_CUDA=ON and a suitable CUDA
architecture. For Vulkan, install its SDK, glslc and SPIRV-Headers.
-DGGML_SOURCE_DIR can select an intentionally reviewed alternative GGML tree.
No build task recursively deletes build/.

## Reference parity checks

tests/parity contains the inherited Torch/NumPy/model-based comparisons.
Builds compile their native harnesses, but startup checks are not numerical parity.
The Python scripts default to `build/native-cpu`, `data/models/` and
`data/checkpoints/`.
Some require a sibling YuE source checkout. Run from tests/parity on Linux.
Historical logs are in reference-logs; they are not evidence for the current image.

## Model tooling

scripts/models retains advanced checkpoint download, conversion and quantization.
These are secondary to inference, not training support. See MODELS.md.
tests/benchmarks/test1.py and tests/fixtures/test1.txt define the repeatable baseline.
Generated artifacts stay under ignored data/results/.
