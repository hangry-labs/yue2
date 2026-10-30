# GGML source snapshot

- Source: https://github.com/ServeurpersoCom/ggml
- Commit: `cc5df49a6b878db2b68b9a7b45976e279594627d`
- License: MIT; see LICENSE and AUTHORS in this directory.
- This is the same patched revision used by the original Yue2 checkout,
  including SNAKE and COL2IM_1D support for the VAE.

The source is vendored as ordinary files. No submodule initialization or nested
Git repository is required. Upstream .github workflows, .pi agent tooling and
the empty .gitmodules file were excluded; runtime source is unchanged.
The MNIST web example's ignore file has two packaging exceptions so its tracked
index.html and ignore file are included when this snapshot is committed.
Snapshot file digests are recorded in ../ggml.snapshot.json.

Update deliberately from a reviewed upstream commit, retain notices, regenerate
the digest manifest and validate CPU/CUDA builds and the generation baseline.
Do not update this dependency with an unreviewed git pull.
