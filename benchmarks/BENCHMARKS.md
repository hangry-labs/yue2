# YuE2 benchmark results

Run `20261101T170052Z-846682fc`, revision `bbc19f2-dirty`, NVIDIA GeForce RTX 5070 Ti. Image `sha256:2c8ed04ae8f7960b8bf46b57c06d9017fbcefde66f8f43f79731b1db9eabb53d`. Isolated inference worker; desktop activity may share the device.

Four areas remain distinct: cold startup, warm generation, sampled GPU memory and lyric fidelity. Model weights stay external and read-only.

Assessment status: **complete**. ASR scores are comparative observations without an absolute acceptance cutoff.

| Suite wall time, through scoring | Seconds |
| --- | --- |
| Total | 349.30 |
| Cold/warmup requests, including downloads | 58.90 |
| Measured requests, including downloads | 252.90 |
| ASR requests | 6.45 |
| Other setup, cleanup and CPU analysis | 31.04 |

Speed, VRAM and lyric scores use the same measured songs. ASR runs afterward on their saved WAVs; warmup songs are excluded from lyric scoring. Report export is outside this wall-time scope.

| Cold phase | Result |
| --- | --- |
| Worker startup (before first generation) | 1.690 s |
| First generation, including weight loads | 39.311 s |
| Successful weight-module loads | 3 |
| Cold sampled device peak | 12747 MiB |

Cold GPU weights do not imply a cold filesystem cache: checksum verification reads model files first.

See [speed](speed/BENCHMARKS.md), [memory](memory/BENCHMARKS.md), [lyrics](lyrics/BENCHMARKS.md), and [methodology](README.md).
