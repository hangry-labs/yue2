# Long-music inference benchmark

Run `20261101T172743Z-89688399`, revision `bbc19f2-dirty`, NVIDIA GeForce RTX 5070 Ti. Image `sha256:2c8ed04ae8f7960b8bf46b57c06d9017fbcefde66f8f43f79731b1db9eabb53d`. Assessment: **complete**.

English, original [long prompt](../fixtures/long-music.txt), 300-second duration ceiling, eight steps and normal 24576 context. Models remain resident; every timed call requires zero weight loads. This suite makes **no ASR requests** and produces no lyric-quality score.

Warmup mode: `short`. 5 warm measured long songs. The first long request after a short warmup can include allocation/graph setup for the longer shapes; these costs remain in its timing. Duration is a ceiling; actual output lengths are measured rather than padded or stretched.

| Seed | Audio s | Pipeline s | Worker s | Client s | Audio s / generation s | Device peak MiB | Loads |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 831001 | 286.24 | 63.15 | 63.43 | 67.56 | 4.53 | 13142 | 0 |
| 831002 | 300.00 | 69.37 | 69.64 | 73.72 | 4.32 | 13089 | 0 |
| 831003 | 300.00 | 70.03 | 70.32 | 74.33 | 4.28 | 13191 | 0 |
| 831004 | 300.00 | 70.58 | 70.92 | 75.43 | 4.25 | 13418 | 0 |
| 831005 | 295.92 | 72.40 | 72.74 | 77.16 | 4.09 | 13329 | 0 |

| Summary | Result |
| --- | --- |
| Pipeline median / p95 | 70.03 / 72.03 s |
| Worker median / client median | 70.32 / 74.33 s |
| Aggregate audio s / generation s | 4.29 |
| Sampled device peak / peak above idle | 13418 / 10821 MiB |
| Retained weight buffers | 3755 MiB |
| Total suite wall time | 430.96 s |
| Cold/warmup requests | 27.48 s |
| Measured client requests | 368.19 s |
| Other setup/cleanup/audio analysis | 35.29 s |

Pipeline excludes output encoding/packaging and HTTP transfer. Worker adds encoding/packaging; client includes the complete download. Sampled nvidia-smi peaks are device-wide lower bounds, including desktop/driver allocations, not exact process/allocator peaks. Total ends after audio integrity analysis; report export is excluded.

Five samples are a controlled local reference, not statistical proof or a before/after speedup claim. This profile is separate from the [30-second multilingual suite](../README.md).
