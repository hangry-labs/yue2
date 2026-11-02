# Two-minute acoustic variations

Run `20261102T181141Z-14c926d8`; image `sha256:80e6c58ff65124fa7f0276c8f3f4e4fb45b387e2f31259a90bab2582c15d910a`; revision `e2d2469-dirty`. NVIDIA GeForce RTX 5070 Ti. Status: **complete**.

English, 120-second ceiling, eight steps, context 24576. Each variation count gets a fresh isolated worker and one excluded full-length warmup. Measured requests must load zero weight modules. The same seeds, lyrics, score and semantic stream are compared across counts. GPU requests remain serial; acoustic variations solve together inside each request.

| Variations | Requests / tracks | Median pipeline s | Pipeline s / track | Audio s / generation s | Device peak MiB | Peak above idle MiB | Median ASR match |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 3 / 3 | 24.62 | 23.55 | 5.10 | 12591 | 9405 | 84.1% |
| 2 | 3 / 6 | 28.33 | 14.09 | 8.52 | 12987 | 9792 | 84.1% |
| 3 | 3 / 9 | 34.27 | 11.27 | 10.65 | 13537 | 10339 | 84.1% |
| 4 | 3 / 12 | 41.33 | 10.16 | 11.82 | 14161 | 11179 | 84.1% |

Device memory is sampled every 100 ms and includes desktop/driver allocations; sampled peaks are lower bounds, not per-process allocator measurements. Warmup and ASR are excluded from pipeline timing. Models stay resident; normal Studio eviction is unchanged.

Each complete rendition is sent to the remote ASR judge after GPU generation. Reference lyrics are never sent as a prompt. ASR match is comparative evidence, not a music-quality grade or an absolute pass/fail threshold. Duration is a ceiling; tracks shorter than 100 seconds are flagged, never padded. Batching need not reproduce single-track waveform bytes.

| Seed | Variations | Track seconds | Pipeline s | Device peak MiB |
| --- | --- | --- | --- | --- |
| 841001 | 1 | 120.00 | 24.62 | 12591 |
| 841002 | 1 | 120.00 | 21.36 | 12584 |
| 841003 | 1 | 120.00 | 24.67 | 12590 |
| 841001 | 2 | 120.00, 120.00 | 28.33 | 12971 |
| 841002 | 2 | 120.00, 120.00 | 26.57 | 12971 |
| 841003 | 2 | 120.00, 120.00 | 29.61 | 12987 |
| 841001 | 3 | 120.00, 120.00, 120.00 | 34.27 | 13537 |
| 841002 | 3 | 120.00, 120.00, 120.00 | 31.64 | 13150 |
| 841003 | 3 | 120.00, 120.00, 120.00 | 35.51 | 13171 |
| 841001 | 4 | 120.00, 120.00, 120.00, 120.00 | 42.42 | 14161 |
| 841002 | 4 | 120.00, 120.00, 120.00, 120.00 | 38.12 | 13904 |
| 841003 | 4 | 120.00, 120.00, 120.00, 120.00 | 41.33 | 13833 |

| Track | ASR match | Technical flags |
| --- | --- | --- |
| m1-measured-00-v1 | 83.4% | none |
| m1-measured-01-v1 | 86.0% | none |
| m1-measured-02-v1 | 84.1% | none |
| m2-measured-00-v1 | 83.4% | none |
| m2-measured-00-v2 | 84.1% | none |
| m2-measured-01-v1 | 86.0% | none |
| m2-measured-01-v2 | 86.6% | none |
| m2-measured-02-v1 | 84.1% | none |
| m2-measured-02-v2 | 83.4% | none |
| m3-measured-00-v1 | 83.4% | none |
| m3-measured-00-v2 | 84.1% | none |
| m3-measured-00-v3 | 83.4% | none |
| m3-measured-01-v1 | 86.0% | none |
| m3-measured-01-v2 | 86.6% | none |
| m3-measured-01-v3 | 86.6% | none |
| m3-measured-02-v1 | 84.1% | none |
| m3-measured-02-v2 | 83.4% | none |
| m3-measured-02-v3 | 84.7% | none |
| m4-measured-00-v1 | 83.4% | none |
| m4-measured-00-v2 | 84.1% | none |
| m4-measured-00-v3 | 83.4% | none |
| m4-measured-00-v4 | 84.1% | none |
| m4-measured-01-v1 | 86.0% | none |
| m4-measured-01-v2 | 86.6% | none |
| m4-measured-01-v3 | 86.6% | none |
| m4-measured-01-v4 | 86.6% | none |
| m4-measured-02-v1 | 84.1% | none |
| m4-measured-02-v2 | 83.4% | none |
| m4-measured-02-v3 | 84.1% | none |
| m4-measured-02-v4 | 84.7% | none |

Total suite wall time: 764.86 seconds, including setup, warmups, audio checks and ASR.
