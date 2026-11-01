# Audio files and FFmpeg

The CUDA image includes FFmpeg. Choose the output format in the studio, or set
`output_format` on `POST /synth` and VAE decode requests. Generated audio stays
48 kHz stereo. A request produces only the selected format; it does not store
duplicate MP3/Opus exports.

| API value | Download | Encoding |
| --- | --- | --- |
| `mp3` | `.mp3` | LAME, `mp3_bitrate` kb/s; default 128 |
| `opus` | `.opus` | Ogg Opus, 96 kb/s VBR |
| `ogg` | `.ogg` | Ogg Vorbis, quality 5 |
| `flac` | `.flac` | Lossless 24-bit PCM |
| `aac` | `.aac` | AAC, 192 kb/s, ADTS container |
| `m4a` | `.m4a` | AAC, 192 kb/s, MP4 container with fast start |
| `wav16` | `.wav` | Uncompressed 16-bit PCM |
| `wav24` | `.wav` | Uncompressed 24-bit PCM |
| `wav32` | `.wav` | Raw 32-bit floating-point PCM; no normalization |

MP3 remains the default. Existing browser preferences are preserved. Opus is
useful for compact listening copies; FLAC/WAV are useful for editing. Lossless
formats preserve the encoded PCM precision, not the original model's latent
representation. Browser playback/preview support depends on the browser's codecs.

All formats except WAV32 retain the existing percentile peak normalization.
Compressed files are encoded directly from float PCM, without an intermediate
lossy file. WAV uses the original native writer, preserving the benchmark path.
MP3 now uses FFmpeg/LAME; old MP3 bytes can differ even with identical PCM.
The standalone `mp3-codec` utility retains its inherited encoder.

## Uploads

The studio's Open action accepts WAV, MP3, Opus/Ogg, FLAC, AAC, M4A/MP4 and WebM,
alongside prompt JSON/YAML and `.vae` latents. Imported recordings keep their
original bytes in the browser library. Downloads retain the correct extension.

Server audio uploads to `/vae`, and to `/transcribe` or `/tokenize` when their
optional models are configured, use the same decoding support. WAV retains its
native decoder; other containers use FFmpeg and become stereo 48 kHz float PCM
before model-specific preprocessing. The first audio stream is selected; video,
subtitles and metadata are not passed into the model. Enabling formats does not
enable or download optional models.

FFmpeg processes receive fixed argument lists without a shell. Input/output files
live in a private temporary directory removed on success, failure or cancellation.
Conversion has a 120-second timeout, and non-WAV upload/decoded/output buffers
are bounded below 512 MiB. Oversized or undecodable input fails rather than
returning a truncated conversion. Network protocols and playlist demuxers are
excluded from upload decoding. Generated-output conversion observes job cancellation.

## Discovery and development

`GET /props` exposes `output_formats`, an array of `{name, extension, mime}`.
Generation results retain the native multipart contract: replay JSON, the selected
audio MIME type, then raw latents for each track. VAE decode returns the selected
audio directly. See the [API reference](ARCHITECTURE.md#endpoints).

The `yue-synth` CLI accepts these formats through its request JSON and derives the
default filename extension accordingly. Direct native users must install FFmpeg
on PATH; server startup checks it before accepting jobs. No FFmpeg development
headers, CUDA dependency rebuild or Python runtime is required by this integration.

`task audio-convert -- input.wav output.opus --format opus` remains available for
converting local files separately. It uses the same encoding presets.

CPU CI (`task check:cpu`) builds `audio-formats-check` and runs
`tests/audio/check_formats.py`. It exercises real codecs, duration/rate/stereo,
24-bit FLAC, upload containers, resampling, malformed input and process timeout/
cancellation without models or a GPU. The normal native startup checks also run.

FFmpeg and its codecs retain their own distribution terms; the runtime keeps
Ubuntu package notices, including a copy of FFmpeg's copyright notice under
`/opt/yue/licenses/ffmpeg.txt`. See [third-party notices](../THIRD_PARTY_NOTICES.md).
