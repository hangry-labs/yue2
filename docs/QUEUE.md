# Queue and result storage

Studio, the music/speech APIs, MCP and optional native tools share **one serial
compute worker**. There is no parallel GPU inference.

## Capacity and retrying

The default limit is **eight accepted jobs, including the active job**. Set
`YUE2_QUEUE_LIMIT` at startup to change it (1–128). All generation routes use the
same atomic admission check. MCP additionally retains its eight-song limit.
Queued cancellation removes that job immediately and releases its slot. Active
cancellation uses the existing engine checkpoints.

Native and compatibility routes refuse excess work with **HTTP 429** and
`Retry-After: 5`. Native errors also include `code` and `retry_after_seconds`;
compatibility errors retain the OpenAI error envelope. MCP returns an
`isError: true` tool result with structured `code: queue_full` and
`retry_after_seconds: 5`, plus the response header; it keeps normal JSON-RPC
transport framing.

Wait at least the indicated interval before retrying a refused submission. Add
jitter and increase the delay on repeated refusals, for example 5, 10, 20 and
30 seconds. A refused submission has not created a job. After acceptance, poll
the returned job instead of submitting the song again. An interrupted connection
can leave an ambiguous outcome; do not blindly replay an expensive request.

## Status and System

`GET /health`, `GET /status` and `GET /system/queue` return the same uncached
snapshot. Health remains HTTP 200 while the queue is full: saturation does not
mean the process needs restarting.

```json
{
  "status": "ok",
  "queue": {
    "limit": 8, "pending": 3, "active": 1, "queued": 2,
    "available": 5, "accepting": true, "retry_after_seconds": 5,
    "rejected": 0, "completed": 4, "failed": 0, "cancelled": 0,
    "active_operation": "synth"
  },
  "results": {
    "location": "volume", "files": 4, "bytes": 2500000,
    "limit_bytes": 10737418240, "limit_files": 256,
    "max_file_bytes": 1073741824, "ttl_seconds": 86400, "full": false
  },
  "http": {
    "workers": 20, "synchronous_limit": 8, "synchronous_waiters": 0,
    "download_limit": 4, "log_stream_limit": 2, "upload_decoder_limit": 2,
    "max_upload_bytes": 67108864
  }
}
```

Counters reset on process restart. Completed result metadata and expiry survive
on the output volume. Snapshots contain aggregate operations, never other callers'
job handles, prompts or lyrics. `GET /props` also advertises the queue configuration.

Native `GET /job?id=ID` now distinguishes `queued`, `running`, `done`, `failed`
and `cancelled`, with `queue_position` (one-based while waiting, zero otherwise).
Completed stored jobs include `expires_at` and existing generation metrics.
Older clients that only recognize `running` as pending must also accept `queued`.
MCP keeps its existing `queued` / `generating` / `complete` states and adds queue
position to pending status.

The **System** tab shows capacity, pending/active counts, rejections and native
result volume usage. Polling runs only while that tab and the document are visible.

## Completed results live on the output volume

Mount `/output` when running the container:

```bash
docker volume create yue2-output
```

Add `--mount type=volume,source=yue2-output,target=/output` to `docker run`.
`task start` already mounts `data/results/studio/` there. Custom bind mounts must
be writable by UID 10001. Without a mount, files live in the container's writable
layer and disappear when that container is removed.

Native/Studio results are stored under `/output/jobs/`: the exact response body
and a small metadata sidecar. This includes audio, multipart replay/latents,
transcription and VAE results. Synchronous API audio is stored once and served
from that same file. MCP writes its single selected export directly to
`/output/agent-artifacts/`, with its existing one-hour capability expiry.

Native result defaults are **24 hours**, **10 GiB total**, **256 files**, and
**1 GiB per result**. Configure these restart-required environment variables:

| Variable | Default | Supported values |
| --- | --- | --- |
| `YUE2_QUEUE_LIMIT` | `8` | 1–128 accepted jobs, including active work |
| `YUE2_RESULT_DIR` | `jobs` relative to the working directory | Writable native result directory; mount it persistently |
| `YUE2_RESULT_TTL_SECONDS` | `86400` | 1–2592000 seconds; fixed from completion |
| `YUE2_RESULT_MAX_BYTES` | `10737418240` | 1 byte–1 TiB total native results |
| `YUE2_RESULT_MAX_FILES` | `256` | 1–10000 retained native results |

Live results are never evicted early to make space. An already-full store refuses
new native/API submissions with HTTP 507. A result exceeding the remaining budget,
the per-file limit, or available disk space fails publication cleanly; it is not
reported complete. Lowering limits preserves existing live results and blocks new
ones until enough space becomes available. MCP's separate 128-file / 2-GiB store
and one-hour links are unchanged.

Expiry is checked on every lookup. Cleanup runs every 30 seconds, before result
publication and at startup. An already-open native download retains a file lease
until delivery ends. Interrupted staging files are removed on restart; unrelated
files are left alone. Job handles retain their original expiry across restarts.
Queued/running work is process-local and is not replayed after a restart.

The server keeps only small job/result metadata in its index. Current inference,
encoding, queued input data and HTTP upload parsing still require working RAM;
completed audio and multipart bodies are streamed from disk in bounded chunks.
The browser's IndexedDB library is separate and remains unchanged. Save downloads
elsewhere for permanent archiving; this volume is a bounded result cache.

Generation's `pipeline_seconds` remains the model-work metric. The worker's
`encoding_packaging_seconds` and `worker_seconds` include result-body serialization
to disk; HTTP delivery and client parsing remain separate. Existing historical
benchmark reports are unchanged.

## Responsiveness and tests

The HTTP server uses 20 fixed workers, at most eight synchronous generation
requests (including their downloads), four additional native/MCP result downloads,
two upload decoders and two log streams. This leaves
capacity for ordinary health, polling and cancellation requests. Payloads are
limited to 64 MiB and socket read/write timeouts are 15 seconds.
Synchronous generation deadlines still include queue time (600 seconds by default).

`task check:cpu` compiles the model-free `server-check` fixture and runs
`tests/server/check_runtime.py`. It tests shared admission, cancellation,
exception recovery, slow writes, storage budgets/expiry, byte ranges, restarts,
eight held synchronous handlers and a burst of 32 refused requests while probing
health. The fixture uses the production queue, storage and HTTP primitives with
an artificial worker; it does not measure model speed or musical quality.

`task test:api` checks the deployed read-only snapshots. Real packaged CUDA/UI
generation is a separate qualification.
