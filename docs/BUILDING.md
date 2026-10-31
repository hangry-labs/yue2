# Reusable CUDA build dependencies

GGML's CUDA kernels are expensive to compile and change much less often than the
app or UI. The Docker build installs them in a separate dependency stage, then
links the app against those libraries. The vendored engine and inference defaults
are unchanged. There is still one runtime image variant, with external weights.

## Local builds

`task build` remains the normal entry point. With targeting set to `auto`, it
prefers the configured pinned distribution artifact or a locally prebuilt one.
Otherwise it detects local GPU targets and reuses/builds that dependency layer.

To prepare an artifact for the broader CI/distribution architecture list:

```text
task deps:plan
task deps:build
```

This builds a local `yue2-ggml:<first-20-characters-of-input-key>` image. It contains
headers, static libraries, CMake exports, build metadata and the GGML license.
It contains no compiler, app, weights or runnable service. The initial cold build
still takes time. App/UI changes do not repeat the CUDA compilation afterward.

Task automatically selects an existing local artifact when its input key and GPU
targets match. For a manual check, use the full tag printed by `task deps:build`:

```text
task build CUDA_ARCHITECTURES="75-virtual;80-virtual;86-real;89-real;120a-real" GGML_DEPS_IMAGE=yue2-ggml:<printed-key-prefix>
```

Explicit narrower architecture lists need their own matching dependency layer.
A single-GPU artifact cannot substitute for the distribution artifact. CUDA
compilation needs the toolkit, not a GPU on the builder.

## Reuse across machines

The artifact is an ordinary OCI image. It can be built locally inside Linux Docker,
pushed to GHCR or another OCI registry, and consumed by CI. Windows-native binaries
are not interchangeable with these Linux libraries.

The prepared manual workflow `.github/workflows/ggml-deps.yml` builds the dependency
only. It publishes to `ghcr.io/hangry-labs/yue2-ggml:<full-input-key>` only when its
`publish` checkbox is explicitly selected. Normal app builds never publish this
package. Its digest is reported in the workflow summary.

For a locally built artifact, an operator can tag and push the printed local tag
to the same registry path. Local GHCR uploads need Docker authentication with
a classic PAT scoped to `write:packages`; GitHub Actions uses its repository
token instead. See [GHCR authentication](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-with-a-personal-access-token-classic).
New GHCR packages default to private, so enable public read access for this
public project's artifact. Inspect the published image to obtain its top-level
OCI digest, then pin it in this checkout:

```text
docker buildx imagetools inspect ghcr.io/hangry-labs/yue2-ggml:<full-input-key>
docker pull ghcr.io/hangry-labs/yue2-ggml@sha256:<published-digest>
python scripts/ggml_deps.py pin --image ghcr.io/hangry-labs/yue2-ggml@sha256:<published-digest>
```

The pin command reads the artifact's metadata without executing it and refuses a
different input key. Review and commit `docker/ggml-deps.json` with the pin. Public
builds need public read access to the package; publishing permissions are separate.
No artifact is published or selected merely by adding this workflow.

CI reads that lock and uses its immutable image reference. The source fallback
works while `image` and `input_key` are null. A stale configured pin fails early
instead of silently using incompatible libraries. To intentionally rebuild from
source, clear both fields, then build and pin the replacement.

## Identity and verification

The input key covers actual GGML source bytes, the dependency CMake wrapper,
metadata/checker scripts, the Dockerfile's dependency stages, pinned CUDA base,
platform and architecture list. App/UI/version stages are outside that boundary.
Compiler flags and ABI definitions belong in the dependency wrapper. Keep the
Dockerfile boundary in place when editing build stages.

Each artifact records the exact compiler and CUDA versions, architecture list,
GGML commit, input key and installed-file SHA-256 hashes in `/opt/ggml/yue2-ggml.json`.
Every app build checks these before linking. The metadata is also included under
`/opt/yue/licenses/` in the runtime. Missing, altered or incompatible artifacts fail
the build. This is compatibility verification, not a signature/trust mechanism;
select artifacts from a trusted registry and pin the digest.

The dependency stage scans its installed files for model weights, and the final
runtime retains its mandatory whole-filesystem weight check. Build tools and
static libraries stay out of the runtime; existing CUDA runtime libraries remain.

## Caches and measurements

GGML output is deliberately a normal image layer. Docker's external layer cache
can reuse it on fresh CI runners; the old cache mounts alone could not do that.
A pinned artifact additionally avoids needing a warm CI layer cache. The compiler
cache remains useful when an intentional dependency update requires rebuilding.

Cold dependency builds, warm dependency reuse, app compilation and registry
transfers are different costs. A prebuilt artifact removes kernel compilation
from app builds but still needs to be downloaded. No GitHub timing improvement
is claimed until the changed workflow has run there.

Local qualification on 2026-10-31 used Docker Desktop with 20 CPUs and about
31 GiB RAM. Two app/UI builds against the same prebuilt distribution artifact
took 68 and 58 seconds, including packaging, with zero CUDA objects compiled.
Base images and local build caches were warm. The source fallback also reused
its compiled GGML layer. These are local checks, not GitHub runner benchmarks.

References: [Docker cache ordering](https://docs.docker.com/build/cache/optimize/)
and [GitHub Actions cache mounts](https://docs.docker.com/build/ci/github-actions/cache/#cache-mounts).
