# Acoustic-variation scaling

Run `20261102T181141Z-14c926d8`; NVIDIA GeForce RTX 5070 Ti; image `sha256:80e6c58ff65124fa7f0276c8f3f4e4fb45b387e2f31259a90bab2582c15d910a`. Matched two-minute English songs, fixed seeds per count, eight steps, resident models. Every count uses a fresh worker and a full-length excluded warmup.

| Variations | Mean batch s | Mean s / rendition | Throughput vs one | Extra batch s / added rendition | Throughput gain over previous | Device peak MiB |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 23.55 | 23.55 | 1.00x | n/a | n/a | 12591 |
| 2 | 28.17 | 14.09 | 1.67x | 4.62 | 67.2% | 12987 |
| 3 | 33.81 | 11.27 | 2.09x | 5.63 | 25.0% | 13537 |
| 4 | 40.62 | 10.16 | 2.32x | 6.82 | 11.0% | 14161 |

Stage means below come from rounded native log summaries, matched to measured job IDs. They are explanatory timings, not GPU kernel profiles. NAR includes acoustic chunk setup/solve; VAE sums all renditions, which decode separately. The residual includes rounding and unlogged work.

| Variations | Score s | Semantic s | Acoustic NAR s | All VAE decodes s | Residual s |
| --- | --- | --- | --- | --- | --- |
| 1 | 7.00 | 11.53 | 4.27 | 0.77 | -0.02 |
| 2 | 6.70 | 11.13 | 8.80 | 1.50 | 0.04 |
| 3 | 6.70 | 11.30 | 13.40 | 2.32 | 0.08 |
| 4 | 7.23 | 11.97 | 18.20 | 3.11 | 0.11 |

Throughput is based on aggregate pipeline time divided by rendered track count. It excludes ASR, cold/warmup requests, encoding and HTTP delivery. Memory peaks are sampled whole-device observations including desktop/driver allocations. More variations share a composition and semantic stream, but have distinct waveform hashes.

Small differences need repetition before being treated as a stable hardware limit. These measurements do not establish memory requirements for five-minute songs, other prompts, or larger batches. ASR remains an imperfect comparative judge. Total original suite wall time, including warmups and ASR: 764.86 seconds. This offline analysis does not alter captured requests, audio, timings or the original run manifest.
