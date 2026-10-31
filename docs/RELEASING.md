# CI and container publication

The publishing workflow targets one weight-free CUDA runtime image in both registries:

- Docker Hub: `hangrylabs/yue2`
- GitHub Container Registry: `ghcr.io/hangry-labs/yue2`

The workflow builds a single image with external weights and uses `master`
as its default branch.
The first publication occurs after pushing this workflow update; configured
image names are not proof that their tags have already been uploaded.

## Tags and triggers

| Trigger | Published tags on both registries |
| --- | --- |
| Push to `master` | `latest` |
| Push matching stable Git tag `vX.Y.Z` | `vX.Y.Z` |
| Manual dispatch, default inputs | `latest` |
| Manual dispatch with `image_tag=vX.Y.Z` | `vX.Y.Z`, plus `latest` when `push_latest` is selected |
| Pull request or another branch | No publication; source validation runs through `ci.yml` |

`latest` is the moving development build and can contain a snapshot version.
Stable tags must exactly match `VERSION` without the snapshot suffix and resolve
to the checked-out commit. Existing stable registry tags are never overwritten.
A stable Git-tag push does not automatically move `latest`.

Manual dispatch accepts an optional existing stable `image_tag`, an optional
`checkout_ref`, and `push_latest` (default true). Checkout defaults to the stable
tag when supplied, otherwise the selected workflow ref. The build uses the exact
checked-out commit for both UI and native version labels. A manual run must
select at least one tag to publish.

## Registry credentials and visibility

The Docker Hub login uses repository secrets `DOCKER_USERNAME` and `DOCKER_TOKEN`.
The account/token must have push access to `hangrylabs/yue2`. Missing credentials
fail before the expensive build. GHCR uses the workflow's `GITHUB_TOKEN` with
`packages: write`; no local Docker login or additional GHCR PAT is required.

Buildx builds once and tags the same image for both registries, including its
provenance and SBOM. The workflow then verifies both top-level OCI index digests
against the build result, followed by an unauthenticated pull-access check. The
verified image references appear in the workflow summary.

A newly created GHCR package defaults to private. For the first publication,
open the package settings and make it public if the anonymous check reports
restricted access. Docker Hub must also allow public pulls. An image can already
have been uploaded when this final visibility check fails; inspect that state
before retrying, especially for an immutable stable tag.

## Validation and build dependencies

`ci.yml` runs tooling tests, source snapshot verification, UI type/format/build
checks and CPU native compilation/startup checks. No model weights are needed.
The CUDA publishing workflow repeats tooling/vendor checks and uses Docker's
mandatory weight-free packaging guard. All actions retain immutable commit pins.

`docker/ggml-deps.json` pins the public GGML release archive. CI verifies the
download and installed files before supplying the named Docker context; a bad
artifact stops the build instead of recompiling CUDA as an automatic fallback.
See [reusable dependencies](BUILDING.md).

Application publication uses inline registry cache metadata. It does not export
the large application/toolchain layers to GitHub Actions cache separately. The
first optimized run spent about 66 seconds in native compilation but 971 seconds
exporting its old GitHub Actions cache; registry publication avoids that duplicate
cache upload. Intermediate toolchain/UI caches may be less effective with inline
caching; the prebuilt GGML archive still removes the expensive CUDA compilation.

## Stable publication

1. Choose a release version in `VERSION` without `-snapshot`.
2. Run `task validate`, `task build` and `task test1`; review artifacts/notices.
3. Commit the reviewed candidate and create its matching `vX.Y.Z` Git tag.
4. Push that tag. The workflow publishes and verifies both registry mirrors.
5. Check public access, then document the readable stable tag with the verified
   top-level OCI index digest. Never substitute a platform child digest.

Publication reports are written to ignored `build/publication/`, retained as a
workflow artifact for 30 days, and summarized on GitHub. Do not invent image digests or claim a GitHub Release
page exists just because a Git tag exists. The `ggml-deps-*` release is a build
dependency, not a product release. There is no full/tiny split or bundled-model
release. Broader CUDA targets remain unqualified beyond the tested RTX 5070 Ti.
