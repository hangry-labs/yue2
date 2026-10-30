# Third-party notices

Hangry Labs YuE2 is based on the MIT-licensed yue2.cpp implementation by the
yue2.cpp authors. Preserve the root LICENSE when redistributing the source.

| Component | License | Source / local notice |
| --- | --- | --- |
| Patched GGML | MIT | [Source](https://github.com/ServeurpersoCom/ggml), vendor/ggml/LICENSE and UPSTREAM.md |
| cpp-httplib | MIT | vendor/cpp-httplib/LICENSE |
| yyjson | MIT | Full notice in vendor/yyjson/yyjson.h |
| minimp3 | CC0 | Dedication in vendor/minimp3/minimp3.h |
| MP3 encoder | MIT | vendor/mp3 headers and root LICENSE |
| Svelte, Vite, TypeScript, Lucide and UI tooling | Their respective upstream licenses | web/package-lock.json pins dependencies; package notices remain in installed packages |

The vendored GGML snapshot is recorded in vendor/ggml.snapshot.json. Its runtime
source is unchanged; upstream CI/agent tooling is excluded.
The runtime image includes the Svelte, Lucide and YAML license texts under
/opt/yue/licenses/web/ alongside native dependency notices.

CUDA container bases and runtime libraries are distributed under their NVIDIA
and dependency terms. The NVIDIA container license remains in the base image.
The application source's MIT license does not replace those terms.

Model weights are not included in the image. YuE2-3B, YuE2-Vae and the optional
MERT/SheetSage/audio-tokenizer models have separate CC BY-NC 4.0 terms. See
[model sources](docs/MODELS.md) and the original model cards. No commercial model
rights are implied by distributing this source code or a weight-free image.
