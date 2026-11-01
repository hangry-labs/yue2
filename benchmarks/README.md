# Generation, memory and lyric benchmarks

The suite follows Faster Qwen3-TTS Studio's separation of speed, GPU memory and
ASR transcript fidelity. It starts a dedicated CUDA Docker worker with external
read-only weights, keeps models resident, and generates original 30-second songs.
The normal Studio retains its standard eviction policy.

The [baseline review](BASELINE_REVIEW.md) explains the measured results and
ASR variability; [generated reports](BENCHMARKS.md) retain the complete tables.

```powershell
task benchmark-plan
task benchmark-test
task benchmark-preflight ASR_URL=http://your-asr-server:8010
task benchmark-smoke ASR_URL=http://your-asr-server:8010
task benchmark-baseline ASR_URL=http://your-asr-server:8010
```

Set `YUE2_ASR_URL` in your ignored `.env` instead of supplying `ASR_URL` each time.
The remote service must expose `/health/ready`, `/v1/models`,
`/v1/audio/supported_languages` and `/v1/audio/transcriptions`. No ASR model is
downloaded or run locally. Docker, Python 3.11+, NVIDIA's `nvidia-smi` and FFmpeg
must be available on the host. Build the selected `IMAGE` with `task build` first.
The harness itself uses only the Python standard library; inference runs in Docker.

The baseline task may stop **this project's idle development server** to free
its GPU allocations. It refuses active/queued jobs and foreign container ownership,
then restarts the exact same container in cleanup, including after a failed run.
It never stops another project's GPU worker. Use a quiet GPU and avoid builds or
other compute during generation. On a desktop, display/driver activity still shares
the device. `--allow-shared-gpu` is available only for diagnostic runs without
`--write-reports`; it cannot update the public baseline.

## Fixed workload

- English and Mandarin Chinese, plus experimental Spanish and German.
- Short, original four-line lyrics, clear solo singing, quiet acoustic accompaniment.
- One fresh composition per request, full score planning, 30-second duration ceiling,
  eight flow-matching steps, normal 24576 context, normal attention and VAE tiling.
- Explicit sampling/CFG/normalization parameters, no adapters, one track, PCM16 WAV.
- One full unmeasured warmup per language. The first is recorded as the cold case.
- Ten measured rounds per language, reversing language order in alternating rounds. Rounds
  one and three repeat identical seeds after intervening languages to detect
  request carryover and measure repeatability. The other rounds use distinct
  fixed seeds: nine distinct seeds plus one repeated control per language.
  Forty measured calls in total, plus four excluded warmups.

Warmups exercise the actual complete pipeline, warming weights, kernels, graph
paths and allocators. All measured calls must report `--keep-loaded`, **zero
weight-module loads**, and at least three resident modules. A worker that reloads
weights fails qualification. Warmups and cold startup never enter warm statistics.
Weights are not sufficient by themselves: warmups also execute the network.

Duration is a ceiling, not a guaranteed musical ending. Each exported song is
checked against 25–31 seconds; early endings or cut-off lyrics remain visible as
flags. The initial six-line English pilot lost its final lines at the 30-second
ceiling. The fixed corpus uses four lines to fit the budget; references are never
shortened to match a transcript after a measured run.

## Measurements and scoring

| Area | Measurement |
| --- | --- |
| Cold | Worker startup and first pipeline request, including model loads |
| Warm speed | Per-language median/p95 pipeline, worker and HTTP client time; RTF and audio seconds per generation second |
| Memory | Whole-device VRAM sampled every 100 ms, peak above idle, resident weight-buffer bytes and retained-memory growth |
| Lyrics | WER, CER, insertions/deletions/substitutions and a comparative 0–100 ASR match score |
| Audio integrity | Actual WAV length/format, peak/RMS, clipping fraction, silence and fixed-seed SHA-256 repeatability |

`GET /job?id=…` publishes immutable timing and residency metadata for completed
generation jobs. The compute worker captures it before publishing `done`; HTTP
threads never access live ModelStore state. Pipeline time excludes output encoding,
packaging, HTTP transport and ASR. With zero weight loads in timed calls, it measures
the resident pipeline including score planning, semantic generation, NAR and VAE.
Worker time adds encoding/packaging. Client time includes request submission,
polling and the full audio download; it is not time to first audio.

Model hashing occurs before timing and warms the filesystem cache. A cold GPU
request therefore does not mean a cold disk cache. GPU figures are sampled device
usage, not exact allocator peaks or process-only memory. Idle subtraction removes
the observed baseline but cannot eliminate desktop noise. Weight-buffer sizes
exclude KV cache, intermediate tensors, workspaces and CUDA overhead.

Speed, memory and lyrics use the **same forty measured samples**. The four
warmup samples are separate and are not ASR-scored. Reports include total suite
wall time, warmup/request time, measured-request time, ASR time and remaining
setup/cleanup/CPU-analysis time. Native pipeline time is included within client
request time; it is not added again. Total wall time ends after scoring, before
report export. Rejudging saved audio preserves the original suite timing.

ASR runs after generation has finished, on the complete music mix converted to
mono 16 kHz. **Reference lyrics are never sent as an ASR prompt.** Case, punctuation
and Unicode width are normalized; accents are preserved. WER uses space-delimited
words for English/Spanish/German; Chinese uses CER without invented segmentation.
Error rates include extra/repeated words and may exceed 100%. Lyric accuracy is
`max(0, 1 − WER) × 100`, or CER for Chinese. The legacy JSON field is named
`lyric_accuracy_percent`; it represents an ASR match score. Missing words count
as alignment differences, including lyrics lost to the duration ceiling.
No absolute score triggers a warning or failure: the judge is imperfect on music,
and an expected score range has not been calibrated. Use matched score deltas
and paired listening to investigate possible degradation. ASR variation alone
does not establish a generation regression or measure musical quality.

## Evidence and reports

Every run writes ignored `data/results/benchmarks/<run-id>/`:

- `run.json`: exact cases/requests, seeds, image ID, source revision, model hashes,
  dependency provenance, GPU/driver, ASR identity, raw timings and memory samples.
- Per-call native WAV, replay JSON and acoustic latents; one copy of each audio file.
- `worker.log`, `RESULTS.md`, `summary.json` and separate speed/memory/lyrics reports.

Warmup/cold outputs are labeled explicitly. Failed runs retain partial evidence.
ASR failures are recorded separately from successful generation. To retry ASR
without running the GPU workload again:

```powershell
task benchmark-score ASR_URL=http://your-asr-server:8010 -- --run data/results/benchmarks/RUN/run.json
```

`benchmark-smoke` runs one language and keeps reports local. `benchmark-baseline`
requires all four languages and at least ten repeats before updating
[the public reports](BENCHMARKS.md). These contain summaries and original-song
transcripts, not audio, private endpoint addresses, host paths or GPU UUIDs.
Low ASR scores remain visible without an absolute pass/fail classification.
Historical raw records retain the old captured warning metadata; current reports
ignore the retired 80% rule without rewriting audio, transcripts or timings.
Report generation does not commit or publish anything.

## Regression checks

Preserve before/after images, run each with the same suite, then compare their raw
`run.json` files:

```powershell
task benchmark-compare -- --before data/results/benchmarks/BEFORE/run.json --after data/results/benchmarks/AFTER/run.json --output data/results/benchmarks/comparison.json
```

Comparison refuses changed harness/corpus/requests/seeds, GPU/driver, model bytes,
ASR model, sample interval or shared-GPU runs. App images/dependency versions may
differ because they are the changes under test. Default gates per language are:

- Median or p95 pipeline latency increase greater than 15%.
- Sampled peak VRAM delta increase greater than 256 MiB.
- ASR score changes are reported as comparative review signals. An opt-in
  `--max-score-drop` gate can be set after calibrating judge/run variability;
  there is no default score-drop failure threshold.
- Additional duration failures, degraded identical-seed repeatability, model
  reloads during timed calls, missing ASR judgments, additional silence/clipping
  failures or excessive retained-memory growth.

Thresholds are explicit comparison options. A failed comparison exits nonzero and
retains its measurements; nothing is relabeled to make it pass. Ten samples per
language are a practical baseline, not statistical proof. Repeat suspicious results on a quiet
machine before attributing a performance difference to code.

The earlier long-song cold baseline remains available as `task test1`; see
[its methodology and history](../docs/BENCHMARKS.md).
