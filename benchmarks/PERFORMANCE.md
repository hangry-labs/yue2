# Where generation time goes

The later [two-minute acoustic-variation qualification](variations/BENCHMARKS.md)
compares one/two renditions with sampled VRAM and full-song ASR. The historical
investigation below retains its original workload and observations.

Investigation on 2026-11-01, RTX 5070 Ti 16 GB, CUDA 12.9.1, eight steps,
full score planning, context 24576 and resident models. Runtime image:
`sha256:2c8ed04ae8f7960b8bf46b57c06d9017fbcefde66f8f43f79731b1db9eabb53d`.
These observations explain the current workload; they do not measure an engine
change or establish a performance regression.

## Existing short and long results

Arithmetic means per request: ten English calls from
`20261101T170052Z-846682fc` and five long calls from
`20261101T172743Z-89688399`.

| Work | Short English prompt | Full long-song prompt |
| --- | ---: | ---: |
| Actual audio | 30.00 s | 296.43 s |
| Score planning, autoregressive | 2.68 s | 13.08 s |
| Semantic music tokens, autoregressive | 2.63 s | 33.76 s |
| Acoustic synthesis, eight flow steps | 0.60 s | 20.22 s |
| VAE audio decoding | 0.19 s | 1.98 s |
| Native pipeline total | 6.13 s | 69.11 s |
| Native output encoding/packaging | 0.020 s | 0.304 s |
| Client time beyond worker and queue | 0.39 s | 4.23 s |
| Audio seconds per pipeline second | 4.90 | 4.29 |

Stages come from saved worker logs matched to job IDs; score/semantic include
prefills, acoustic includes chunk setup, VAE uses tiled decoding logs.
Rounding and unattributed work leave about 0.03/0.07 seconds per short/long call.
Native totals/encoding use higher-resolution job metrics. Warmups are excluded.

The short benchmark is slightly faster per second of audio. These suites use
different lyrics, styles and seeds: their difference is descriptive, not a
matched duration experiment. Longer acoustic sequences also cost more per frame:
roughly ten times the audio took 34 times the acoustic stage time here. A kernel
profile is needed to assign that increase to individual operations.

## Same lyrics, different duration limits

Diagnostic `20261101T175347Z-duration-stages` used the original
[long prompt](fixtures/long-music.txt), both seeds 831001 and unchanged settings.
After one excluded full-pipeline warmup, only the duration limit changed. The
existing 300-second result for that seed is a reference from the earlier session.

| Duration ceiling | Score tokens | Score | Semantic | Acoustic | VAE | Pipeline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 s, first | 2814 | 12.2 s | 3.0 s | 0.7 s | 0.19 s | 16.19 s |
| 30 s, repeat | 2814 | 12.1 s | 3.2 s | 0.7 s | 0.18 s | 16.15 s |
| 120 s | 2814 | 12.3 s | 12.2 s | 5.0 s | 0.80 s | 30.28 s |
| 300 s, earlier session, 286.24 s actual | 2814 | 11.9 s | 30.8 s | 18.5 s | 1.89 s | 63.15 s |
| 30 s, explicitly supplied score | skipped | skipped | 3.1 s | 0.7 s | 0.18 s | 4.00 s |

The duration limit applies to the semantic frame budget, after planning. It is
absent from the score prompt: the planner still composes from all supplied
lyrics. All three fresh diagnostic takes produced the same ABC score. Planning
consumed about 75% of the short take with the full song's lyrics. This is useful
composition work, but a short duration limit does not make that work smaller.

The supplied-score probe sent the first take's ABC explicitly, with the original
lyrics, style and seeds; it did **not** supply semantic tokens. It reproduced the
30-second WAV byte for byte in 4.00 seconds instead of 16.15–16.19. This measures
the existing deliberate score-reuse path, not fresh composition. Normal Generate
must continue to create a new score; automatic reuse would change that behavior.
Repeated fresh 30-second output was also byte-identical.

All measured diagnostic calls reported zero loads and three resident modules.
The cold warmup took 29.00 seconds and loaded three modules; it includes loading
and first-use initialization. Production uses strict eviction by default, whereas
these measurements use `--keep-loaded`. They do not estimate production reload costs.

## Sharing work and concurrency

The dependency chain is score → semantic tokens → acoustic latents → audio
decode → packaging. Acoustic synthesis consumes the AR stage's KV cache, so
these stages cannot simply run independently within one fresh song.

- **Two acoustic variations:** `synth_batch_size=2` produced two 30-second
  renditions in **6.72 seconds total**. Score/semantic work ran once; acoustic
  synthesis took 1.2 seconds and both VAE decodes totaled 0.37 seconds. These
  share a composition and semantic stream, rather than being independent songs.
  This is one exploratory observation, without a musical-quality assessment.
  The first batched rendition differed from its single-track counterpart;
  batching is not a byte-identical replacement.
- **Two independent queued requests:** fixed English requests were submitted
  sequentially, queued, queued, then sequentially. Pair wall times were
  **11.24/10.62/10.74/10.84 seconds**. WAV hashes matched per seed in all four
  pairs. The second queued job waited 4.6–4.8 seconds before computing. HTTP
  result handling can overlap the next job, while GPU work stays serial. The
  roughly 3% pair-wall difference includes execution variance; it is not
  evidence of parallel inference or a robust speedup estimate.

Independent-composition batching already exists as `lm_batch_size` when the
server has sufficient `--max-batch`. It was **not qualified** here. That is a
useful next experiment before arbitrary cross-request batching. Larger batches
need more KV/workspace memory; the long benchmark already reached 13418 MiB
device-wide on this 16 GB card, including desktop/driver allocations.

Adding compute threads requires separate request execution state, KV/cache
ownership, graph/scheduler ownership and a deliberate memory/residency policy.
The server currently has one mutable pipeline and ModelStore. A mutex around
the store alone would not make overlapping execution safe.

## End-of-request work

Native WAV encoding/packaging averages about 0.3 seconds for a long song, under
0.5% of its native generation time. The Python client additionally downloads
and parses audio, replay metadata and latents; this is separate from inference.

An offline check reconstructed native multipart layout from archived bytes and
verified the decoded WAV, latent bytes and replay metadata were unchanged:

| Result | Multipart body | Python MIME parsing, mean of two | WAV integrity analysis, one call |
| --- | ---: | ---: | ---: |
| 30.00 s | 5.96 MB | 0.13 s | 0.42 s |
| 286.24 s | 56.84 MB | 1.24 s | 3.76 s |

These separate CPU measurements do not decompose the earlier live HTTP timing.
Remaining live overhead was not isolated into network, polling, buffering and
parsing. The browser uses a different binary parser, so Python costs do not
measure Studio playback readiness. Suite integrity analysis scales with total
audio samples rather than being a fixed generation delay.

## Next experiments

1. Measure independent-composition batches of two against matched single-song
   requests, including VRAM, lyric fidelity and cancellation. Preserve normal
   context and fresh-request behavior.
2. Profile score and semantic token loops separately. Planning dominates short
   takes made from full-song lyrics. Separate sampling, host/device
   synchronization and GPU execution before choosing an optimization.
3. If adding a short-composition mode, make planning duration-aware and evaluate
   structure and lyrics. Cutting the score token budget can truncate a score;
   it is not a transparent performance fix.
4. Improve benchmark transport/CPU analysis separately if suite throughput
   matters. Preserve native pipeline timing as the inference metric.

No engine defaults, reuse rules, eviction policy, benchmark baselines or dependency
artifacts changed. No ASR was called. Raw diagnostic requests, metadata/hashes,
logs and timings remain in ignored `data/results/benchmarks/diagnostics/`.

Implementation: [pipeline](../src/pipeline.h), [prompt](../src/prompt.h),
[token loop](../src/generate.h), [worker](../src/cli/yue-server.cpp),
[ownership](../src/model-store.h),
[transport](https://github.com/hangry-labs/yue2/blob/master/benchmarks/runtime.py),
[audio analysis](https://github.com/hangry-labs/yue2/blob/master/benchmarks/metrics.py).
