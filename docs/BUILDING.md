# Reusable CUDA build dependencies

Normal `task build` and CI download a **99 MB, checksum-pinned GitHub Release
archive** of the compiled GGML/CUDA libraries. They compile the current app and UI
against that installation. No registry login is needed to download the public
archive. There is still one runtime image variant, with external model weights.

## Normal builds

```text
task deps:plan
task deps:prepare
task build
```

The first two commands inspect the lock and optionally warm the dependency cache;
`task build` performs those checks automatically. The cache lives under ignored
`build/ggml-release/<archive-sha256>/`. Subsequent builds verify and reuse it.

The lock in `docker/ggml-deps.json` records the versioned asset URL, exact download
size, archive SHA-256 and dependency input key. It currently points to
[the tested GGML dependency release](https://github.com/hangry-labs/yue2/releases/tag/ggml-deps-486cfbc9cab44f7eb35f).
It uses that specific asset, never the latest-release endpoint. The adjacent
uploaded `.sha256` file is useful for manual downloads; builds trust the checksum
committed in the lock rather than fetching a replacement checksum from the server.

The downloader checks the compressed bytes before extraction. It rejects unsafe
paths, links, special files, duplicate members and excessive payload size. It then
checks the source/options key, installed-file hashes and absence of weights.
Docker repeats the source, compiler/CUDA and file checks before linking the app.
A missing, modified or incompatible configured artifact fails the build. It does
not trigger a long source compilation as an automatic recovery step.

With GPU targeting set to `auto`, Task uses the released distribution targets
when they cover the detected GPU. Explicit narrower targets and GPUs outside
that list retain a separate matching source dependency path. Those builds can
still require an initial CUDA compilation.

## How CI consumes the archive

The container workflow prepares the dependency before starting Docker. The
verified installation is supplied as the `selected-ggml` named build context,
overriding the dependency-image stage. This works with a fresh Buildx builder;
no locally loaded Docker image or retained native compiler cache is required.
The vendored GGML compile stages are outside that consumer's build graph.

The archive contains `opt/ggml/`: public headers, static libraries, CMake exports,
license and `yue2-ggml.json` provenance metadata. Its roughly 233 MB unpacked payload
contains no compiler, application, build tree or model weights. Build tools and
standalone static archives stay out of the final runtime image; GGML code is
linked into the native executables. The final whole-image weight guard remains
mandatory.

Plain `docker build .` uses the source dependency stages unless an artifact image
or named context is explicitly supplied. Use Task for the automatic release
archive path. See [Docker runtime commands](DOCKER.md).

## Refreshing the dependency release

Rebuild only after an intentional GGML, ABI/options, toolchain or GPU target
change. C++17, inference defaults and the existing distribution targets are
preserved by the current package.

```text
task vendor:verify
task deps:build
task deps:export
```

`deps:build` deliberately compiles the dependency from source, even while a
release archive is configured. The initial cold compilation is expensive. It
creates `yue2-ggml:<first-20-characters-of-input-key>` in local Docker.
`deps:export` verifies and exports that installation into
`data/results/build-deps/<key-prefix>/`, producing a `.tar.gz` and matching `.sha256`.
These generated binary files remain outside Git source control.

Upload both files to a separate GitHub Release tagged `ggml-deps-<key-prefix>`.
Use a prerelease and leave the product's latest-release label unset. Update the
lock's input key and archive URL, size and SHA-256 from the verified export.
Commit the matching build recipe before creating its dependency tag. A
`ggml-deps-*` tag does not match the product's `v*.*.*` publication trigger.

Then run `task test`, `task build` and the GPU `task test1` baseline. Qualify the
actual uploaded download before considering the lock ready. A stale archive pin
fails early while the replacement is being prepared; `deps:build` and `deps:export`
remain available to produce it. To deliberately build the app entirely from
source, clear `archive`, `image` and `input_key` in the lock.

## Identity and alternative transport

The input key covers actual GGML source bytes, the shared ABI definitions,
dependency CMake wrapper, metadata/checker scripts, dependency-only Docker stages,
pinned CUDA base, platform and architecture list. App/UI/version edits and release
transport changes do not invalidate those compiled libraries. Keep the Dockerfile
fingerprint boundary and shared ABI definitions intact.

Metadata records the GGML commit, exact compiler/CUDA versions, target list, input
key and installed-file SHA-256 hashes. It is also copied into `/opt/yue/licenses/`
in the runtime. Checksums and metadata verify consistency; artifact hosting and
reviewed locks establish which binary to trust.

The OCI artifact image remains an optional transport. The manual
`.github/workflows/ggml-deps.yml` workflow builds it and publishes to GHCR only
when its publish input is selected. This is not required by normal builds.
To use a registry artifact instead of the release archive, clear `archive`, then
pin the actual published digest:

```text
python scripts/ggml_deps.py pin --image ghcr.io/hangry-labs/yue2-ggml@sha256:<published-digest>
```

Local GHCR uploads require separate package-write credentials; public read access
is needed for unauthenticated builds. Native Windows binaries cannot substitute
for these Linux Docker-built libraries.

## Caches and measurements

The source fallback also keeps installed GGML in an ordinary Docker layer,
which external layer caches can retain. Cache mounts alone are not preserved
by GitHub Actions caching. The release archive avoids depending on a warm
layer cache or a one-time cold CI kernel compilation.

Normal application publication attaches inline cache metadata to its registry
images and imports it from the published `latest` tags. It avoids a separate
large GitHub Actions cache upload: the first optimized CI run spent 971 seconds
exporting that cache after native compilation finished in about 66 seconds.
Inline caching retains less intermediate build state than `mode=max`; the
precompiled GGML release remains the primary reuse mechanism.

Local qualification on 2026-10-31 used Docker Desktop with 20 CPUs and about
31 GiB RAM. Two app/UI builds against the prebuilt distribution image took
68 and 58 seconds, including packaging, with zero CUDA objects compiled.
Base images and local build caches were warm. These are local checks, not GitHub
runner benchmarks. The eight-step generation baseline produced byte-identical
score, tokens, latents and MP3; this is not an inference speed improvement claim.

References: [Docker named contexts](https://docs.docker.com/reference/cli/docker/buildx/build/#build-context),
[cache ordering](https://docs.docker.com/build/cache/optimize/), and
[GitHub Actions cache mounts](https://docs.docker.com/build/ci/github-actions/cache/#cache-mounts).
