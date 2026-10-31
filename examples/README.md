---
layout: default
title: Song examples guide
permalink: /examples/guide/
---
# Song examples

[Listen to the gallery](https://hangry-labs.github.io/yue2/examples/) or open
`examples/index.html` from a downloaded checkout. The players, artwork, prompts
and recordings work locally without a CDN. The website uses the same gallery
inside the shared Hangry Labs documentation theme.

## The recordings

Four original prompts explore acoustic pop, synth pop, folk and ambient music.
The English lyrics were written for this gallery; the ambient prompt supplies
no lyrics and requests instrumental music. No reference recordings or cloned
voices were used. Descriptions such as voice character, genre and tempo express
what was requested, rather than guaranteed properties of the resulting music.

Every recording uses the Q8 generation model and F32 VAE, full score mode,
8 flow-matching steps and separate fixed composition/noise seeds. The duration
ceiling is 180 seconds for the vocal requests and 120 seconds for the ambient
request. Some songs finish sooner; reaching the ceiling can cut a song short.
The published MP3s are the generated output, without trimming or post-production.

These examples demonstrate sound and prompting, not a timing benchmark or a
guarantee of exact words, instrumentation or reproducibility across machines.
Model terms remain separate from the application license. See
[models and terms](../docs/MODELS.md).

## Reuse a prompt

Each card provides its requested musical direction, lyrics, settings and seeds.
Select **Copy request** or download **Prompt JSON**. In your local studio,
select **Open** and load that file, then edit it. Clear the seeds for a fresh
draw; leave them fixed to repeat the request with the same software and models.

**Replay JSON** additionally contains the generated score and audio codes.
After opening it, explicitly choose **Replay audio codes** to render the existing
performance, or **Use ABC score** to reuse its written tune. Normal **New song**
starts from the text and direction without reusing generated conditioning.

## Definitions and provenance

[definitions.json](definitions.json) is the authored source. It holds song titles,
descriptions, musical direction, lyrics, seed choices and shared generation settings.
[assets/manifest.json](assets/manifest.json) records the actual engine/image identity,
measured model hashes, requests, generation times, MP3 format/duration, decoded
waveform peaks and file sizes/SHA-256 digests. Public recipes live in `recipes/`.

`catalog.js` embeds that manifest so a downloaded gallery also works through
`file://` without fetching JSON. The player loads audio only when requested,
pauses the previous song, supports seeking and saves only its listening-volume
preference in this browser. There is no connection to a visitor’s local studio.

Fingerprints use UTF-8 JSON with sorted keys, no extra whitespace and normalized
LF newlines in text, so checkout line endings do not change the definition hash.
Media digests hash the exact published bytes. Waveforms contain 96 peak bins
from a mono 2 kHz decode of each published MP3; they are display data, not audio.

## Generate and verify

After provisioning the models and building the local image:

```text
task examples-generate
task examples-verify
```

Generation requires Docker with NVIDIA GPU support and host FFmpeg/FFprobe. It
starts an isolated temporary CUDA container from `yue2:dev`, binds the models
read-only, and writes only this gallery. It does not replace the development
server or change its settings/browser library. The temporary server is removed
when the command finishes. Requests run sequentially.

Matching completed recordings are reused only after their recipes, model/image
identity and every asset checksum pass verification. A partial run can be
resumed with the same command. Metadata-only waveform refreshes reuse the audio.
Changing a definition requires a matching new recording; the verifier rejects
stale metadata instead of silently rewriting its checksum.

For the integrated site, run `task pages` and open
<http://127.0.0.1:9005/yue2/examples/>. `task pages-test` checks the real site
build and media without loading models. See the [website guide](../docs/WEBSITE.md).
