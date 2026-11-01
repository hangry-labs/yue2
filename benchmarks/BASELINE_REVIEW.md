# Ten-sample resident-model baseline observations

Run `20261101T170052Z-846682fc` completed **ten measured songs per language** and
four separate full warmups on an RTX 5070 Ti 16 GB: forty measured requests in
total. Each language used nine distinct seeds plus one repeated control. Durations
ranged from 28.64 to 30.00 seconds; every request used eight flow-matching steps
and reported **zero model loads** with three resident modules. All four repeated
controls reproduced identical WAV bytes after intervening requests. No measured
call triggered a duration, mostly-silent-audio or clipping warning.

The run is **complete** under the current assessment policy. ASR values are
comparative reference observations; no expected score range or absolute lyric
acceptance threshold has been established for this judge on music.

| Language | N | Warm pipeline median | Pipeline p95 | Median ASR match | ASR match range |
| --- | --- | --- | --- | --- | --- |
| English | 10 | 5.88 s | 7.39 s | 94.7% WER-based | 89.5–100.0% |
| Mandarin Chinese | 10 | 5.33 s | 5.90 s | 82.1% CER-based | 35.7–89.3% |
| Spanish, experimental | 10 | 6.97 s | 9.33 s | 70.0% WER-based | 40.0–95.0% |
| German, experimental | 10 | 5.38 s | 6.33 s | 85.0% WER-based | 75.0–100.0% |

ASR matches varied by language and seed, including a large spread for Mandarin.
These observations do not identify whether a difference came from the generator,
the sung delivery or the judge. Keep all samples and transcripts for matched
future comparisons and paired listening. The judge was Qwen3-ASR 0.6B on the full
music mix. Its expected variability has not been calibrated, so a lower score
alone is not a generation-quality verdict. ASR score decreases are comparative
review signals, without an absolute acceptance threshold.

Total suite wall time was **349.30 seconds (5m 49s)** through the end of
scoring: 58.90 seconds for cold/warmup requests, 252.90 seconds for the forty
measured requests, 6.45 seconds for ASR requests and 31.04 seconds for other
setup/cleanup/CPU work. Native pipeline execution within the measured requests
totaled 236.52 seconds; it is included in the 252.90 seconds, not additional time.
Speed, VRAM and lyric measurements use the same forty measured WAVs. No extra
songs were generated for ASR. Report export is outside this recorded scope.

The maximum sampled whole-device memory was **12,929 MiB**, including the desktop
and driver. Peak above the pre-worker idle reading was **9,229 MiB**. Retained
model weight buffers totaled **3,755 MiB**; the difference includes KV caches,
intermediate storage, workspaces and other device allocations. Device usage fell
197 MiB between the end of warmups and the end of measurements. Device-wide
changes also include background activity; this is not an allocator leak test.

The expanded seed coverage changes the measured distributions. The earlier
three-sample run `20261101T160657Z-e3e87e56` remains in local raw evidence; it is
not a matched before/after comparison with this forty-sample workload. Use this
ten-sample profile for subsequent comparisons. There is no engine speedup or
ASR-quality regression claim from changing the sample count.

See [methodology](README.md), [speed](speed/BENCHMARKS.md),
[memory](memory/BENCHMARKS.md), [transcripts and fidelity](lyrics/BENCHMARKS.md),
and [machine-readable summary](BASELINE.json). Audio and complete raw evidence
remain in the local run directory under `data/results/benchmarks/`.
