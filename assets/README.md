# Product artwork

Optimized WebP files live in
[`web/src/assets/`](https://github.com/hangry-labs/yue2/tree/master/web/src/assets) so Vite embeds the artwork in the local
studio without external image requests.

| File | Role |
| --- | --- |
| `yue2_logo_horizontal.webp` | Expanded studio header, project README and Docker Hub overview |
| `yue2_logo.webp` | Examples dialog |
| `yue2_badge.webp` | Optional product watermark for documentation/showcase artwork |
| `yue2_mascot.webp` | Empty song library illustration |
| `yue2_favicon.webp` | Browser tab and compact studio header |

The first four WebPs preserve the source dimensions and alpha channel, using
WebP quality 90. The 128 × 128 favicon is derived from the mascot. The separate
Hangry Labs logo remains the small Powered by signature.

Source artwork is archived separately. Put newly supplied PNGs in the ignored
`build/artwork-input/` directory, then regenerate with Python and FFmpeg's
`libwebp` encoder installed:

```text
task assets:build
task web:build
```

Normal Docker builds use the committed WebPs and need no image-conversion tools.
After all conversions and alpha checks pass, the helper removes project-local
PNG inputs. It preserves external originals when invoked with `--source-dir`.
PNG source archives are not kept in this repository. Documentation
screenshots belong in `screenshots/` and should reflect the current interface.
