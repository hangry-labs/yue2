# CI and container publication

There is one weight-free CUDA image variant. No registry image has been
published as part of this repository cleanup.

## Validation

.github/workflows/ci.yml runs on pull requests, master pushes and manual dispatch:
- Python tooling/lifecycle/publication tests and vendor snapshot verification.
- Svelte/TypeScript checks, formatting and current UI build.
- CPU Docker compilation and startup checks for all eight native executables.

No model weights or GPU are needed in those checks. Historical numerical parity
logs are not a substitute for current validation.

.github/workflows/docker-build.yml builds the linux/amd64 CUDA runtime on master,
version tags and manual dispatch. Branch builds do not publish. Publication occurs
only for a matching stable version tag or an explicit manual publish selection.
Actions are pinned to immutable commits. Builds use BuildKit layer caching,
provenance and SBOM generation.

## Stable publication

1. Select a release version in VERSION without the -snapshot suffix.
2. Run task validate, task build and task test1; review artifacts and notices.
3. Review the source, commit it, and create the matching vX.Y.Z Git tag.
4. Pushing that tag triggers publication to ghcr.io/hangry-labs/yue2:vX.Y.Z.

The tag must match VERSION. The workflow uses GITHUB_TOKEN with packages:write;
the repository's GHCR/package permissions must allow publication. This configures
a future publication path; it does not establish that an image already exists.
Docker Hub publication is not configured.

Manual workflow dispatch defaults publish to false. An explicit publish can use
latest or another valid container tag. Stable tags are not automatically moved
to latest. Do not invent registry digests in documentation; verify the published
OCI index before adding a stable run command.

The general CUDA architecture list is broader than the locally tested RTX 5070
Ti baseline. Qualify supported hardware before presenting it as a release matrix.
No full/tiny image split or bundled-model release is configured.
