# Models and provenance

task models downloads or verifies the two files required for song generation.
Models remain in the host models/ directory and outside the image.

models/manifest.json pins the GGUF publisher revision
e630f2b8f6aedf8254c3186438633c1b5eeaf80a and each file's SHA-256/size.

| File | Size | Purpose |
| --- | --- | --- |
| YuE2-3B-Q8_0.gguf | 3.81 GB | AR/NAR backbone and embedded text tokenizer |
| YuE2-Vae-F32.gguf | 530 MB | Audio encoder/decoder |

The downloader resumes partial files, checks integrity and atomically installs
completed files. Existing incorrect files cause a visible failure and are not
silently overwritten. For offline use, provision the same files manually and
run task models to verify them; valid files need no network access.

## Optional components

The upstream engine additionally supports:
- MERT-v2-FullSong-Q8_0.gguf, approximately 902 MB.
- SheetSage2-Q8_0.gguf, approximately 106 MB.
- yue2-mothersuperior-realaudio-tokenizer-v4-Q8_0.gguf, approximately 47 MB.

Place a head next to its MERT encoder with matching quantization. Enable the
heads through --transcriber and --tokenizer server arguments. They are not part
of the default download manifest or default startup, and are not required to
generate from lyrics. Additional backbone quants exist upstream; the local
baseline uses Q8_0. The VAE stays F32.

## Advanced conversion

The original inference conversion utilities are retained under scripts/models/:
checkpoints.sh fetches original checkpoints, convert.py creates GGUFs, and
quantize.sh generates the supported quants. Run them from the repository using
their new paths. Conversion requires Python packages gguf/numpy and hf for
downloads. Some original checkpoint repositories require accepting their terms
and authentication. Do not put credentials into source or images.

The conversion paths are root checkpoints/ and models/. The quantization script
defaults to build/native-cpu/quantize; override YUE2_BUILD_DIR for another build.
These tools do not provide training or fine-tuning support.

## Licenses and original sources

The original model cards and GGUF publisher state CC BY-NC 4.0:
- [YuE2-3B](https://huggingface.co/m-a-p/YuE2-3B)
- [YuE2-Vae](https://huggingface.co/m-a-p/YuE2-Vae)
- [MERT-v2-FullSong](https://huggingface.co/m-a-p/MERT-v2-FullSong)
- [SheetSage2](https://huggingface.co/m-a-p/SheetSage2)
- [Mothersuperior audio tokenizer](https://huggingface.co/Mothersuperior/yue2-mothersuperior-realaudio-tokenizer-v4)
- [GGUF publisher](https://huggingface.co/Serveurperso/YuE2-GGUF)

The native engine's MIT license does not grant commercial rights to the model
weights. Keeping weights external does not change their use restrictions.
