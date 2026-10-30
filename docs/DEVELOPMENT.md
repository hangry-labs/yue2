# Development

The primary workflow uses Docker for C++/CUDA builds and Node UI checks.
Host dependencies are Docker/Buildx, NVIDIA GPU support, Python 3.11+ and Task.
Python helpers use the standard library; Python is not added to the inference image.

## Task interface

| Command | Behavior |
| --- | --- |
| task doctor | Inspect Docker, Buildx and host GPU visibility |
| task models | Verify/download pinned external models |
| task init | Models, then CUDA image build |
| task build | Rebuild current native engine and UI |
| task start | Start the default server or replace an older project image |
| task stop / status / logs | Operate this project's container |
| task test | Tooling tests and GGML snapshot verification |
| task check:cpu | Compile all native targets and check executable loading in Docker |
| task web:check | Check Svelte/TypeScript and formatting in Node Docker |
| task web:build | Regenerate the embedded UI asset in Node Docker |
| task validate | Tooling, vendor, UI and CPU checks |
| task test1 | Full GPU generation baseline |
| task test1:prepare | Prepare the request without Docker inference |

Task configuration is in Taskfile.yml; implementation is in scripts/dev.py.
Defaults match .env.example. CLI variables override local settings.
Only the named project container is replaced. Start refuses replacement while a
known job is running and does not stop another project's container with that name.
Changing images restarts the process and clears its in-memory jobs/results.
Models and browser data persist.

Local builds detect host NVIDIA compute capability when possible and compile for
that hardware. Set CUDA_ARCHITECTURES explicitly for a different build. Docker
builds have no GPU access, so do not pass the CMake value native to Docker builds.
The Dockerfile's broader architecture default is for distribution builds and
has not been qualified as a support matrix.

## Build stages and caching

Dockerfile stages:
- web: Node 24 checks and builds the current Svelte source.
- source: selects source files; excludes models and local state.
- cpu-checks: compiles all native targets and verifies startup without weights.
- build: C++17/CUDA 12.9.1 compilation with CMake, Ninja and ccache.
- runtime: CUDA runtime, native executables, notices and embedded UI.

BuildKit cache mounts retain native object files and compiler cache locally.
Rebuilds still configure dependencies; source or compiler changes invalidate
affected files. The caches contain no model weights.

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
The Python scripts default to build/native-cpu and external models/checkpoints.
Some require a sibling YuE source checkout. Run from tests/parity on Linux.
Historical logs are in reference-logs; they are not evidence for the current image.

## Model tooling

scripts/models retains advanced checkpoint download, conversion and quantization.
These are secondary to inference, not training support. See MODELS.md.
benchmarks/test1.py and tests/fixtures/test1.txt define the repeatable baseline.
Generated artifacts stay under ignored results/.
