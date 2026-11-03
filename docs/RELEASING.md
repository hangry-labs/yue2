# CI and container publication

The publishing workflow targets one weight-free CUDA runtime image in both registries:

- Docker Hub: `hangrylabs/yue2`
- GitHub Container Registry: `ghcr.io/hangry-labs/yue2`

## Current stable release

[v1.0.0](https://github.com/hangry-labs/yue2/releases/tag/v1.0.0) was published on
November 3, 2026 from commit `a8df40ba3e7d2a5417a2645f8ef91f72a9022fc9`.
[Workflow 41702398585](https://github.com/hangry-labs/yue2/actions/runs/41702398585)
verified matching registry indexes and public pull access:

```text
hangrylabs/yue2:v1.0.0@sha256:446bd69099513f8b1d762656d455826872b7221ab232aa05e907f3ada90c9b34
ghcr.io/hangry-labs/yue2:v1.0.0@sha256:446bd69099513f8b1d762656d455826872b7221ab232aa05e907f3ada90c9b34
```

The release assets include `images.json` with immutable references and
`validation.json` with the qualification summary. Model weights are external.

## Publication history and policy

The workflow builds a single image with external weights and uses `master`
as its default branch.
The first application publication completed successfully in
[run 41218835258](https://github.com/hangry-labs/yue2/actions/runs/41218835258)
at commit `05ff1f077d85dafe566dd82b6f7fea06e5188aca`. Both `latest` mirrors
reported the same top-level OCI index when checked. `latest` continues to move;
this does not represent a stable version release.

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

`ci.yml` runs tooling tests, source-pin verification, UI type/behavior/format/build
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

## Docker Hub overview

The registry overview is maintained in [dockerhub.md](dockerhub.md), with absolute
links and image URLs that work outside GitHub. Copy its Markdown into the
`hangrylabs/yue2` repository's **Overview** on Docker Hub. The GitHub publishing
workflow uploads images and verification reports; it does not synchronize this
description. See [Docker's repository information guide](https://docs.docker.com/docker-hub/repos/manage/information/).

Suggested short description:

```text
Local YuE2 song generation with a browser studio and HTTP API. CUDA; external models.
```

Keep the overview aligned with the README's model downloads, runtime commands,
tag policy and license notes. When product artwork or UI screenshots are added,
use repository-relative paths in the README and absolute raw GitHub URLs here.
Do not add gallery, website or translation links before those pages exist.
