# Project website

The [public website](https://hangry-labs.github.io/yue2/) renders the repository
README, documentation and [song gallery](https://hangry-labs.github.io/yue2/examples/)
with the same Hangry Labs theme used by Faster Qwen3-TTS Studio. Markdown and
gallery definitions remain the content sources; there is no second overview
to keep synchronized.

## Preview and check

```text
task pages
task pages-test
task pages-stop
```

The preview is <http://127.0.0.1:9005/yue2/>. It runs in the project-owned
`yue2-pages-preview` container, so it does not leave a terminal process running.
The stop task refuses a container with someone else’s ownership label. Change
the preview port with `python scripts/pages.py preview --port 9006` if needed.

`task pages-build` builds without starting a preview. The build uses a separate
pinned Ruby/Jekyll image with Pages-compatible plugins and safe mode enabled.
These tasks do not start inference, download model weights or use the GPU.
The song generator is a separate explicitly invoked task.

`task pages-test` checks the actual generated pages, internal routes, Markdown
rendering, private-file exclusions and exact gallery media/recipe digests. Browser
checks should additionally cover desktop/mobile navigation, tables, code copy,
audio playback, seeking, volume/mute, pause-previous and request downloads.

## Content and theme

`_config.yml` owns the title, production origin, `/yue2` base path, navigation,
source branch and exclusions. English, Norwegian Bokmål, Polish, Japanese,
Simplified Chinese and Spanish have translated READMEs and documentation
introductions. Detailed technical guides retain English text with an explicit
fallback notice. See [localization](LOCALIZATION.md) for catalogs, locale routes
and the distinction between interface language and original song content.

The Apache-2.0 theme lives in `site/theme/`, retaining its license. It provides
the common header, responsive section sidebar, language router, readable tables,
copyable code and reduced-motion behavior. Product logos stay in the existing
`web/src/assets/` location. The theme’s optional favicon and source-path settings
allow this project’s logo and excluded-source GitHub links without changing its
shared visual design.

The listening page uses `examples/index.md` as a thin wrapper around the
standalone gallery’s main element. The raw HTML is excluded from Jekyll output
to avoid colliding with the wrapper’s `/examples/` route. Both versions use the
same scoped styles, player, catalog and audio. The [examples guide](../examples/README.md)
has its own `/examples/guide/` route. The [documentation index](README.md) is `/docs/`.

The gallery separates musical-style and lyric-language filters from website
language. Playback and download share one Ogg Opus file per song, targeting
modern browsers with Ogg Opus support.
New recordings retain 24-bit PCM in ignored local data for further conversions;
the public site contains compressed listening copies and their recipes.
`task examples-convert` verifies or refreshes Opus exports without inference, and
`task audio-convert -- input.wav output.flac --format flac` converts local files.

## Public inputs and deployment

The local build stages Git’s tracked and nonignored public files, including
uncommitted edits, through an explicit public-content allowlist. Private files,
credentials and links escaping the checkout are rejected before replacing the
previous stage. Source/output are confined to ignored `build/pages/`. The hosted
build also has explicit exclusions for local data, weights, code, tests, builder
inputs and private context. The Pages builder and gallery are excluded from the
CUDA image’s Docker context.

GitHub Pages is already configured to build the root of `master`. Pushing these
files through the normal review flow lets that existing Pages deployment build
the themed site; no remote theme download or new publication workflow is needed.
A local preview of uncommitted edits is not a public deployment.
