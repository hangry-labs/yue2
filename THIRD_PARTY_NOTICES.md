# Third-party notices

Hangry Labs YuE2 is based on the MIT-licensed yue2.cpp implementation by the
yue2.cpp authors. Preserve the root LICENSE when redistributing the source.

| Component | License | Source / local notice |
| --- | --- | --- |
| Hangry Labs Pages theme | Apache-2.0 | Adapted from Faster Qwen3-TTS Studio; [local license](site/theme/LICENSE) |
| GGML 0.28.0 | MIT | [Official source](https://github.com/ggml-org/ggml/tree/v0.28.0), [local notice](vendor/licenses/ggml-MIT.txt) |
| cpp-httplib 0.64.0 | MIT | [Upstream](https://github.com/yhirose/cpp-httplib/tree/v0.64.0), [notice](vendor/licenses/httplib.txt) |
| yyjson 0.13.0 | MIT | [Upstream](https://github.com/ibireme/yyjson/tree/0.13.0), [notice](vendor/licenses/yyjson.txt) |
| minimp3 | CC0 | [Pinned upstream](https://github.com/lieff/minimp3/tree/ea99364f61c14656440e8d77e9c233ccf3124633), [notice](vendor/licenses/minimp3.txt) |
| Inherited MP3 encoder | MIT, with CC0 table sources | src/codecs/mp3 headers and root LICENSE; table provenance is retained in tabs_data.h |
| FFmpeg and packaged codecs | Upstream and Ubuntu package terms, including GPL/LGPL components | [FFmpeg](https://ffmpeg.org/), runtime `/usr/share/doc/ffmpeg/copyright` and `/opt/yue/licenses/ffmpeg.txt` |
| Svelte, Vite, TypeScript, Lucide and UI tooling | Their respective upstream licenses | web/package-lock.json pins dependencies; package notices remain in installed packages |

The official GGML archive is pinned by commit and SHA-256 in
`docker/ggml-source.json`. Source builds download it into their build directory;
normal CUDA builds reuse the separately verified precompiled artifact.
No GGML runtime source patches are applied. Our CMake configuration supplies the
ABI and backend settings. GGML's MIT notice is retained in the source repository
and compiled distribution; the full GGML source is not vendored here.
The runtime image includes the Svelte, Lucide and YAML license texts under
/opt/yue/licenses/web/ alongside native dependency notices.

`docker/app-deps.json` pins the HTTP library, JSON library and MP3 decoder by
upstream commit and archive checksum. Their sources are fetched into build
storage, with no local runtime patches. Docker caches their compiled libraries
and installed headers separately from the application. Their license notices and
the dependency lock are copied into `/opt/yue/licenses/` in the runtime image.

CUDA container bases and runtime libraries are distributed under their NVIDIA
and dependency terms. The NVIDIA container license remains in the base image.
The application source's MIT license does not replace those terms.

Model weights are not included in the image. YuE2-3B, YuE2-Vae and the optional
MERT/SheetSage/audio-tokenizer models have separate CC BY-NC 4.0 terms. See
[model sources](docs/MODELS.md) and the original model cards. No commercial model
rights are implied by distributing this source code or a weight-free image.
