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

Ten original prompts explore acoustic pop, synth pop, folk, ambient, techno,
country, metal, J-pop, Latin pop and Mandopop. The English, Japanese, Spanish and
Mandarin lyrics were written for this gallery; ambient and techno supply
no lyrics and request instrumental music. No reference recordings or cloned
voices were used. Descriptions such as voice character, genre and tempo express
what was requested, rather than guaranteed properties of the resulting music.

Every recording uses the Q8 generation model and F32 VAE, full score mode,
8 flow-matching steps and separate fixed composition/noise seeds. The duration
ceiling is 180 seconds for the vocal requests and 120 seconds for the ambient
request. Some songs finish sooner; reaching the ceiling can cut a song short.
The original four recordings were generated as MP3 and converted to Opus.
New recordings retain the generated 24-bit PCM locally and encode Opus directly
from that source, without trimming, fades or loudness changes. PCM sources stay
outside the public repository. Only the Opus files are published.

The [upstream model card](https://huggingface.co/m-a-p/YuE2-3B) lists English and
Chinese. Japanese and Spanish are experimental language requests, not a claim
of officially supported singing languages. The language filter selects the
requested lyric language, independently of the English website navigation.

Offline Qwen3-ASR-1.7B checks on 30-second excerpts recovered matching lyric
lines in all four vocal languages. Japanese and Spanish text was transcribed
in the requested language even though the recognizer labeled those excerpts
English; some words also differed. This is encouraging evidence from excerpts,
not a full-song pronunciation or lyric-accuracy assessment by fluent listeners.

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
measured model hashes, requests, generation times, audio format/duration, decoded
waveform peaks and file sizes/SHA-256 digests. Public recipes live in `recipes/`.
Each song retains its actual generation engine identity; adding songs with a
new build does not relabel or regenerate earlier recordings.

Playback and downloads share one **Ogg Opus file at 96 kb/s VBR** (`.opus`)
per song. The gallery targets modern browsers with Ogg Opus support.
Codec, container, source digest and FFmpeg version/settings are recorded for
every conversion. The `.opus` extension already uses the Ogg container.
The first four recordings have a lossy MP3 source; conversion cannot recover
detail discarded by that original encoding.

`catalog.js` embeds that manifest so a downloaded gallery also works through
`file://` without fetching JSON. The player loads audio only when requested,
pauses the previous song, supports seeking and saves only its listening-volume
preference in this browser. There is no connection to a visitor’s local studio.

Fingerprints use UTF-8 JSON with sorted keys, no extra whitespace and normalized
LF newlines in text, so checkout line endings do not change the definition hash.
Media digests hash the exact published bytes. Waveforms contain 96 peak bins
from a mono 2 kHz decode of each published Opus preview; they are display data, not audio.

## Generate and verify

After provisioning the models and building the local image:

```text
task examples-generate
task examples-convert
task examples-verify
```

Generation requires Docker with NVIDIA GPU support and host FFmpeg/FFprobe. It
starts an isolated temporary CUDA container from `yue2:dev`, binds the models
read-only, and writes only this gallery. It does not replace the development
server or change its settings/browser library. The temporary server is removed
when the command finishes. Requests run sequentially.

Matching completed recordings are reused only after their recipes, model/image
identity and every asset checksum pass verification. Earlier engine identities
remain attached to their own recordings; use `--force` to refresh selected songs
deliberately after an engine change. A partial run can be
resumed with the same command. Metadata-only waveform refreshes reuse the audio.
Changing a definition requires a matching new recording; the verifier rejects
stale metadata instead of silently rewriting its checksum.

`task examples-convert` needs no model or GPU. It reuses matching verified Opus
exports. Changing encoding requires the retained original source; it never
re-encodes an Opus file into another lossy copy. New PCM sources are kept under
ignored `data/results/gallery-masters/`. Verification rejects duplicate or
unreferenced audio exports in the public music folder.

## Convert other local audio

The same verified profiles support Opus, Ogg Vorbis, MP3, FLAC, WAV16, WAV24,
floating-point WAV32, AAC and M4A:

```text
task audio-convert -- input.wav output.opus --format opus
task audio-convert -- input.wav output.ogg --format ogg
task audio-convert -- input.wav output.flac --format flac
task audio-convert -- input.wav output.m4a --format m4a
```

FFmpeg and FFprobe must be on `PATH`. The converter checks the actual output
codec, channels, duration and complete decode before installing it. It refuses
to replace the input or an existing output unless `--overwrite` is explicit.
FLAC and WAV are lossless storage formats; exporting a lossy source into them
does not restore missing information. Use a generated WAV/PCM source for archival
conversion. Conversion preserves duration and applies no fades or normalization.

For the integrated site, run `task pages` and open
<http://127.0.0.1:9005/yue2/examples/>. `task pages-test` checks the real site
build and media without loading models. See the [website guide](../docs/WEBSITE.md).
