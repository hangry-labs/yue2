# Recorded generation metadata

Completed synthesis results include a versioned snapshot of how that particular
track was generated. Store it alongside the audio for future inspection. These
are recorded output facts, not additional generation controls.

## Where to read it

- MCP `get_song`: `generation` with the existing completed-song fields. It is
  persisted with the artifact across repeated reads and restarts until the
  existing one-hour expiry. The four tools and their inputs stay compatible.
- Native `GET /job?id=ID`: `generations`, an array in song-major, variation-minor
  order. Each JSON replay part in a synthesis result also includes its track's
  `generation`. Existing replay fields and audio/latent parts stay compatible.
- `/v1/audio/music` and `/v1/audio/speech`: still binary audio. The existing
  `X-YuE2-Job-ID` header and new `Link: </job?id=ID>; rel="describedby"` identify the
  native metadata response, with normal native retention (typically 24 hours).

Existing access boundaries apply: optional Bearer authentication covers `/v1`
and `/mcp`; native `/job` belongs to the local studio API. Remotely exposing the
native API needs the deployment's existing access controls. MCP introduces no
additional metadata lookup or cross-job capability.

`Generation` in `/openapi.json` describes the object. New snapshots have
`schema_version: 1`. Legacy results without recorded facts return
`generation: null` (MCP) or `generations: null` (native). Do not backfill from
today's models, build identity or `/props` defaults.

## Fields

| Field | Recorded meaning |
| --- | --- |
| `model`, `decoder` | Filenames, quantization and tensor storage-type counts from GGUF descriptors read at execution; no absolute paths. |
| `serving.version`, `serving.revision` | Build used for this job; unknown revision is `null`, local dirty build identifiers remain visibly dirty. |
| `base_seed`, `seed` | Resolved acoustic base and this variation's actual noise seed. |
| `base_lm_seed`, `lm_seed` | Resolved LM base and this song's semantic-token seed. Token replay has no consumed `lm_seed`, so it is `null`. |
| `planning` | Effective `mode` (`full`/`melody`/`off`), score `source` (`generated`/`supplied`/`none`), `base_seed`, final `seed`, `retries_used` and configured `retry_limit`. No generated plan means null planning seeds. |
| `tempo` | Explicit structured hint (`mode: hint`, `hint_bpm`) or no hint (`mode: automatic`, `hint_bpm: null`). `measured_bpm` is currently always `null`. |
| `steps`, `guidance` | Refinement count and resolved semantic CFG strength. Automatic sentinels become numbers; replay guidance is `null`. |
| `sampling.planning`, `sampling.semantic` | Actual sampler configurations, including semantic budget clamping for duration/continuation. Skipped stages are `null`. |
| `semantic_source` | `generated`, `continuation` or `replay`. |
| `song_index`, `variation_index` | Zero-based track coordinates; MCP currently produces 0/0. |
| `duration_ceiling_seconds`, `truncated` | Requested ceiling and whether planning or semantic generation exhausted its budget, not a quality score. |
| `adapters`, `adapter_count`, `adapters_complete` | Public adapter IDs and merge strengths; zero scale leaves weights unchanged. No resolved adapter paths. |
| `audio` | Output format/rate/channels, speed, source duration and applicable normalization/MP3 settings. `peak_clip` is the effective value clamped to 0-999. |

All seeds are **decimal strings or `null`** to preserve signed 64-bit precision
through JavaScript clients. Store the strings directly rather than converting
through a JavaScript `Number`. Random-mode sentinels are never resolved seeds.

A retry does not replace the semantic seed: planning can finish with 102 after
two retries while semantic generation still uses 100. Keep both `lm_seed` and
`planning.seed`; their distinction is intentional.

Model `quantization_source` distinguishes a GGUF `general.file_type` declaration
from `dominant_tensor_storage` (largest tensor-byte share). Mixed storage appears
in `tensor_types`. A numeric GGUF declaration is also retained as `gguf_file_type`.
Quantization is never guessed from a filename suffix. These IDs are not content
hashes and cannot guarantee reproduction after model/adapter files or hardware
and software change.

Tempo automatic means no explicit MCP `tempo_bpm` argument, not a fixed BPM or
analysis of free-text style. A 112 BPM hint does not prove measured 112 BPM audio.

For ordinary exports, `audio.duration_seconds` is derived from generated PCM
samples, before encoder padding. After speed adjustment it is unmeasured here:
`duration_seconds` is `null`, with `duration_estimate_seconds`,
`source_duration_seconds` and an explicit `duration_basis`. Encoder padding can
affect container durations. Raw `wav32` has no normalization or effective
`peak_clip` value.

## Example

The `generation` value below illustrates a completed Opus track with a 30-second
ceiling and a 112 BPM style hint. Seeds and build revision are illustrative;
this is not a release identity or a promise of measured tempo.

```json
{
  "schema_version": 1,
  "model": {
    "filename": "YuE2-3B-Q8_0.gguf",
    "tensor_types": [
      {
        "type": "F32",
        "count": 229
      },
      {
        "type": "Q8_0",
        "count": 398
      }
    ],
    "quantization": "Q8_0",
    "quantization_source": "gguf.general.file_type"
  },
  "decoder": {
    "filename": "YuE2-Vae-F32.gguf",
    "tensor_types": [
      {
        "type": "F32",
        "count": 435
      }
    ],
    "quantization": "F32",
    "quantization_source": "dominant_tensor_storage"
  },
  "serving": {
    "version": "1.0.0",
    "revision": "example-build-revision"
  },
  "base_seed": "831001",
  "seed": "831001",
  "base_lm_seed": "831002",
  "lm_seed": "831002",
  "planning": {
    "mode": "full",
    "source": "generated",
    "base_seed": "831002",
    "seed": "831002",
    "retries_used": 0,
    "retry_limit": 2
  },
  "tempo": {
    "mode": "hint",
    "hint_bpm": 112,
    "measured_bpm": null
  },
  "steps": 8,
  "guidance": 1.0,
  "semantic_source": "generated",
  "sampling": {
    "planning": {
      "temperature": 0.699999988079071,
      "top_p": 0.8999999761581421,
      "top_k": 30,
      "repetition_penalty": 1.0049999952316284,
      "penalty_window": 100,
      "min_tokens": 32,
      "max_tokens": 4096
    },
    "semantic": {
      "temperature": 1.0,
      "top_p": 0.949999988079071,
      "top_k": 100,
      "repetition_penalty": 1.2000000476837158,
      "penalty_window": 50,
      "min_tokens": 200,
      "max_tokens": 750
    }
  },
  "song_index": 0,
  "variation_index": 0,
  "duration_ceiling_seconds": 30.0,
  "truncated": true,
  "adapter_count": 0,
  "adapters": [],
  "adapters_complete": true,
  "audio": {
    "format": "opus",
    "sample_rate": 48000,
    "channels": 2,
    "source_duration_seconds": 29.998666666666665,
    "speed": 1.0,
    "duration_seconds": 29.998666666666665,
    "duration_basis": "generated_pcm_samples",
    "normalization": "percentile_peak",
    "peak_clip": 10
  }
}
```

## Bounds and ownership

Each generation object is bounded to 16 KiB. Adapter detail is limited to 16 entries
and 8 KiB of serialized detail. Larger lists return `adapters: null`, their actual count and
`adapters_complete: false`. MCP permits no adapter overrides and reports an
empty list. Unknown legacy facts stay unknown.

Snapshots are allowlisted by the compute worker. GET handlers read the saved
snapshot, not current configuration. Lyrics, style, scores, token streams,
credentials, guide/download capabilities and directory paths are excluded from
`generation`. The outer MCP URL and expiry stay unchanged. Capturing these facts
does not regenerate old songs, alter inference settings or extend retention.
