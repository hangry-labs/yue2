// Compile against the fetched GGML header, not a copy of the scan kernel.
// Run in a separate process under compute-sanitizer. No model files required.
#include "fattn-common.cuh"
#include <cstdio>
#include <cstdlib>
#include <vector>

static void check(cudaError_t status) {
    if (status != cudaSuccess) {
        std::fprintf(stderr, "CUDA: %s\n", cudaGetErrorString(status));
        std::exit(2);
    }
}

int main(int argc, char ** argv) {
    const int masks = argc > 1 ? std::atoi(argv[1]) : 1;
    const int sequences = argc > 2 ? std::atoi(argv[2]) : 2;
    const int keys = argc > 3 ? std::atoi(argv[3]) : 512;
    if (masks < 1 || sequences < masks || sequences % masks != 0 || keys < 256 || keys % 256) return 2;
    constexpr int columns = 32;
    std::vector<half> host(keys * columns * masks, __float2half(-INFINITY));
    // Distinct nonmasked key lengths test broadcasting AND per-sequence masks.
    for (int m = 0; m < masks; ++m)
        for (int q = 0; q < columns; ++q)
            for (int k = 0; k < (m % 2 ? keys : 256); ++k)
                host[(m * columns + q) * keys + k] = __float2half(0.0f);
    half * mask = nullptr;
    int * result = nullptr;
    // Separate allocation: a pooled allocation can hide an out-of-bounds read.
    check(cudaMalloc(&mask, host.size() * sizeof(half)));
    check(cudaMalloc(&result, sequences * sizeof(int)));
    check(cudaMemcpy(mask, host.data(), host.size() * sizeof(half), cudaMemcpyHostToDevice));
    flash_attn_mask_to_KV_max<columns><<<dim3(1, sequences), FATTN_KQ_STRIDE / 2>>>(
        (const half2 *) mask, result, keys / FATTN_KQ_STRIDE,
#ifndef YUE2_UNPATCHED_MASK_SCAN
        masks,
#endif
        keys / 2, keys * columns / 2);
    check(cudaGetLastError());
    check(cudaDeviceSynchronize());
    std::vector<int> output(sequences);
    check(cudaMemcpy(output.data(), result, sequences * sizeof(int), cudaMemcpyDeviceToHost));
    check(cudaFree(result));
    check(cudaFree(mask));
    for (int s = 0; s < sequences; ++s) {
        const int expected = (s % masks) % 2 ? keys : 256;
        if (output[s] != expected) {
            std::fprintf(stderr, "sequence %d: expected %d, got %d\n", s, expected, output[s]);
            return 1;
        }
    }
    std::printf("PASS: %d masks broadcast over %d sequences, %d keys\n", masks, sequences, keys);
}
