# Sampled GPU memory

Run `20261101T170052Z-846682fc`, revision `bbc19f2-dirty`, NVIDIA GeForce RTX 5070 Ti. Image `sha256:2c8ed04ae8f7960b8bf46b57c06d9017fbcefde66f8f43f79731b1db9eabb53d`. Isolated inference worker; desktop activity may share the device.

Requested device sampling interval: 0.100 s. These are whole-device nvidia-smi observations, not allocator or per-process peaks. A sampled peak is a lower bound; display/driver/background allocations remain included. Delta subtracts the idle device reading after the development server stopped and before the worker started. Weight buffers come from the compute worker and exclude KV cache, activations and workspaces.

| Language | Sampled device peak MiB | Peak above idle MiB | Resident weights MiB | Timed module loads |
| --- | --- | --- | --- | --- |
| en | 12836 | 9136 | 3755 | 0 |
| zh | 12836 | 9136 | 3755 | 0 |
| es | 12929 | 9229 | 3755 | 0 |
| de | 12856 | 9156 | 3755 | 0 |

Retained whole-device memory changed by -197 MiB from the end of all warmups to the end of measured calls; background changes can affect this value.
