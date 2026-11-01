# Inherited MP3 encoder

This encoder is part of the original yue2.cpp implementation, retained under
the application's MIT license. It is project source, rather than a separately
released third-party dependency. The move from `vendor/mp3/` preserves its code.

`mp3enc.h` provides encoding; the other headers implement bit packing, filtering,
transforms, quantization and coding tables. `gen_huff_enc.c` and `tabs_data.h`
are table-generation helpers, not normal runtime build inputs. The table source
identifies its minimp3 CC0 origin. Preserve those notices and the root license.

MP3 decoding is provided separately by the checksum-pinned upstream minimp3
dependency in `docker/app-deps.json`.
