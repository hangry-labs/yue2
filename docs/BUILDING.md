# Reusable CUDA build dependencies

Normal `task build` and CI download a **checksum-pinned GitHub Release archive**
of the compiled official GGML 0.28.0/CUDA libraries. They compile the current app and UI
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
[the GGML 0.28.0 dependency release](https://github.com/hangry-labs/yue2/releases/tag/ggml-deps-cc43a4cc92197996f17c).
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
The GGML download/compile stages are outside that consumer's build graph.

The archive contains `opt/ggml/`: public headers, static libraries, CMake exports,
license and `yue2-ggml.json` provenance metadata. Its unpacked payload
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
task deps:verify
task deps:build
task deps:export
```

`deps:build` deliberately compiles the dependency from source, even while a
release archive is configured. The initial cold compilation is expensive. It
creates `yue2-ggml:<first-20-characters-of-input-key>` in local Docker.
`deps:export` verifies and exports that installation into
`data/results/build-deps/<key-prefix>/`, producing a `.tar.gz` and matching `.sha256`.
These generated binary files remain outside Git source control. Export also
produces a small build-recipe archive and checksum containing the exact Dockerfile,
source pin, CMake settings, metadata/checker tools and license notices. It contains
no fetched GGML source or weights and reproduces the dependency input key.

Upload the dependency, recipe and their checksums to a separate GitHub Release
tagged `ggml-deps-<key-prefix>`.
Use a prerelease and leave the product's latest-release label unset. Update the
lock's input key and archive URL, size and SHA-256 from the verified export.
Prefer a tag at the matching committed recipe. For a dependency published before
the application changes are committed, the attached recipe is the authoritative
rebuild input; the tag only anchors the dependency release in repository history.
Rebuild it with `docker build --target ggml-deps .` from the unpacked recipe. A
`ggml-deps-*` tag does not match the product's `v*.*.*` publication trigger.

Then run `task test`, `task build` and the GPU `task test1` baseline. Qualify the
actual uploaded download before considering the lock ready. A stale archive pin
fails early while the replacement is being prepared; `deps:build` and `deps:export`
remain available to produce it. To deliberately build the app entirely from
source, clear `archive`, `image` and `input_key` in the lock.

## Identity and alternative transport

The input key covers the checksum-pinned GGML source archive identity, the shared ABI definitions,
dependency CMake wrapper, metadata/checker scripts, dependency-only Docker stages,
pinned CUDA base, platform and architecture list. App/UI/version edits and release
transport changes do not invalidate those compiled libraries. Keep the Dockerfile
fingerprint boundary and shared ABI definitions intact.

Metadata records the GGML commit, exact compiler/CUDA versions, target list, input
key and installed-file SHA-256 hashes. It is also copied into `/opt/yue/licenses/`
in the runtime. Checksums and metadata verify consistency; artifact hosting and
reviewed locks establish which binary to trust.

## Official source and local overrides

`docker/ggml-source.json` pins official version 0.28.0, its exact commit and source
archive SHA-256. Source builds use CMake FetchContent to verify that archive before
unpacking it under their build directory. No full GGML source is committed here.
There are no GGML source patches in this release. Our overrides are the C++17/ABI
settings in `cmake/ggml-abi.cmake` and CUDA/backend settings in `cmake/ggml-deps/`.

The first source build needs network access; its downloaded source is reused by
that build directory. Normal artifact consumers do not fetch the source at all.
MIT license/copyright notices remain in `vendor/licenses/ggml-MIT.txt` and the
distributed artifact/runtime. Updating the source pin requires a new compiled
artifact; the old binary must not be relabeled to match new source.

Moving source out of Git does not fix vulnerabilities. Source-only scanning of
tracked files cannot assess the downloaded GGML implementation. A build-based
security analysis must include that fetched source; CPU analysis also does not
qualify unused GPU backends. Existing CodeQL alerts need separate triage/rescanning.

## Other native dependencies

`docker/app-deps.json` pins cpp-httplib 0.64.0, yyjson 0.13.0 and minimp3 commit
`ea99364f61c14656440e8d77e9c233ccf3124633`. Every package has an exact upstream
archive checksum and retained license notice. `cmake/app-deps.cmake` uses upstream
CMake projects for HTTP/JSON and an interface target for the decoder header.
No third-party source is kept in `vendor/`; that folder holds license notices.
The inherited project MP3 encoder lives under `src/codecs/mp3/`.

The Docker `app-deps` stage downloads and compiles these small libraries once per
lock/configuration/toolchain change. Application and UI edits reuse that layer.
The application imports the installation with `YUE2_APP_DEPS_PREFIX`; its lock is
checked before linking. CPU/native source builds fetch the same pinned archives
under their build directory. Native builds need Python 3 for upstream httplib's
header splitting. HTTPS/compression extras remain disabled as before.

These small libraries do not need a separate binary release. Their updates leave
the GGML dependency fingerprint and its existing published artifact unchanged.
`task deps:verify` checks all native pins and retained notices. Dependency updates
still require HTTP/API, decoder and generation testing; fetching newer sources
alone is not a security audit. Build-based security scanning must include these
downloaded sources too; scanning tracked files alone cannot assess them.

## Roll back to the previous GGML dependency

The previous fork artifact remains published and is never overwritten or deleted:
[previous dependency release](https://github.com/hangry-labs/yue2/releases/tag/ggml-deps-486cfbc9cab44f7eb35f).
`docker/ggml-rollback.json` retains its exact archive checksum, input key, source
commit and matching application checkout. Keep the old release and its assets.

Use a separate checkout of that recorded revision for a complete compatible
rollback, leaving current work untouched:

```text
git worktree add --detach build/ggml-rollback 12cfefee2c2520ebec5059e9bacfc91f80e32204
cd build/ggml-rollback
task build IMAGE=yue2:ggml-rollback
```

That checkout uses the old source snapshot and old artifact identity checks.
Do not paste its input key into the new lock or weaken verification to mix versions.
Starting a rollback image is a separate action; finish active jobs before replacing
a running server. No task automatically deletes previous dependency releases.

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
