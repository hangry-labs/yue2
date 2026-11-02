# Shared attention-mask regression

`shared-mask.cu` includes the **actual fetched GGML CUDA header** and launches its
mask-scan kernel with separately allocated masks. It needs no model weights.
Build with CUDA 12.9.1 against the source selected by `docker/ggml-source.json`:

```sh
nvcc -std=c++17 -O2 -arch=sm_120a -lineinfo \
  -Xcompiler=-ffunction-sections -Xlinker=--gc-sections \
  -I"$GGML_SOURCE/include" -I"$GGML_SOURCE/src" -I"$GGML_SOURCE/src/ggml-cuda" \
  tests/cuda/shared-mask.cu -o shared-mask
compute-sanitizer --tool memcheck --error-exitcode 99 ./shared-mask 1 2
```

Select the architecture for your GPU. Run each case in a separate process:
mask/sequence pairs `1 1`, `1 2`, `1 4`, `2 2`, `2 4`. Success requires both correct
per-sequence scan limits and **zero sanitizer errors**. On pristine official
v0.28.0, compile with `-DYUE2_UNPATCHED_MASK_SCAN` for the old kernel signature;
`1 2` reproduces the invalid global read. The fixture deliberately uses a
512-key aligned length that enables the problematic scan. An optional third
argument selects another aligned key count; test 256 and 1024 too. It tests the scan,
not the full attention operation or musical quality.

Real generation is qualified separately with `task benchmark-variations` using
two-minute songs. The normal 30-second lyric suite and five-minute no-ASR suite
retain their existing profiles.
