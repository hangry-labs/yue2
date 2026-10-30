# Repeatable generation baseline

```text
task test1
```

Requires the built local image and models. It runs benchmarks/test1.py against
tests/fixtures/test1.txt in a temporary Docker container, independently of the UI
server. Do not run competing generation jobs when comparing timings.

## Fixed profile

- Full symbolic score generation.
- Upstream 24576-token context and normal eviction, attention and VAE tiling.
- 360-second duration ceiling, one track.
- 8 flow-matching steps.
- LM and acoustic seeds 831001.
- Q8_0 backbone, F32 VAE, MP3 128 kbps.

The 360-second limit is a ceiling; the model may stop earlier.
An approximately five-minute song in approximately one minute is a comparison
target, not a hard assertion. Fixed seeds do not guarantee byte-identical audio
across GPU/toolchain changes.

Use task test1 LM_SEED=123 SEED=456 IMAGE=yue2:dev to select a different profile
explicitly. task test1:prepare writes the request without starting inference.
Rebuild the image after engine changes; the task does not silently rebuild it.

## Artifacts and timing

Each ignored results/test1/<UTC timestamp>-<suffix>/ directory contains:
- Original prompt and exact request JSON.
- MP3, replay JSON, ABC score, semantic CSV and VAE latents.
- Native generation log and summary.json.

Summary records actual image ID/revision label, model SHA-256 hashes, GPU,
seeds, pass/fail, generated duration, wall time and pipeline time.
Model hashing precedes timing and warms the filesystem cache. Wall time includes
Docker startup, model loading, inference and encoding. Native pipeline timing
excludes final MP3 encoding and uses rounded log values.

Success checks native completion, nonempty audio, score/semantic replay data and
the requested 8-step setting. Musical quality is not automatically evaluated.
Failed generation returns a failing task exit code and retains evidence.

## Initial measured baseline

2026-10-30, RTX 5070 Ti 16 GB, CUDA 12.9.1, fixed profile above:

| Measurement | Result |
| --- | --- |
| Generated audio | 270.8 s (4m 31s) |
| Pipeline | 85.1 s |
| Total wall | 90.5 s |
| End condition | Model end token; duration cap not reached |

This is one local result, not a performance guarantee or cross-hardware claim.

After the repository reorganization, the same fixed profile produced 270.8 s
of audio in 79.3 s pipeline / 84.3 s wall time. The ABC score, semantic tokens,
latents and MP3 were byte-identical to the initial baseline on this machine.
The timing difference is not claimed as an engine speed improvement.
