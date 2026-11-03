# Interface and documentation languages

YuE2 uses the same interface locales as the Faster Qwen3-TTS Studio reference:
English (`en`), Norwegian Bokmål (`nb`), Polish (`pl`), Japanese (`ja`), Simplified
Chinese (`zh`) and Spanish (`es`). English is the default. Interface language is
independent of lyric language, model capabilities and the gallery's lyric filter.

## Studio

Use the language selector in the header or open `/en`, `/nb`, `/pl`, `/ja`, `/zh`
or `/es`. The corresponding `/LOCALE/docs` route opens the API view. A direct
locale URL takes precedence over the saved browser preference. Switching updates
the existing page, keeping lyrics, direction, settings, library and active jobs.
Browser storage is optional; the English shell and explicit locale routes work
without it. All catalogs are bundled into the standalone HTML, with no CDN or
translation service. Unknown diagnostics retain their original text.

The sources are `web/src/lib/i18n.ts`, `i18n.svelte.ts` and the six JSON catalogs
under `web/src/lib/locales/`. Wrap interface text with `msg`, keep interpolation
placeholders identical across languages, and translate accessible labels and help
as well as visible controls. Use `feedback` for known diagnostic wrappers. Never
translate user text, API keys, enum values, filenames or musical notation as a
side effect of switching locale. Keep UI requests rooted at `/` so trailing-slash
locale URLs do not change endpoint resolution.

## Website and README

The root README and five `README.LOCALE.md` files are the overview sources.
Localized documentation introductions are `docs/README.LOCALE.md`. They render
through the shared Pages shell; relative links and explicit language choices
use the page map rather than a second HTML documentation copy.

Detailed technical reference pages currently remain in English. The site keeps
the selected navigation language and shows a fallback notice when a document
has no translation. Add a translated guide using the same `.LOCALE.md` suffix
and an explicit `lang`; do not label English body text as translated.

The listening gallery's interface and descriptions are translated in the bundled
`examples/locales.js`. Original titles, lyrics, musical directions, recordings
and downloaded recipes retain their source language. A locale change preserves
the active player, seek position, volume and musical/lyric filters.

## Validation

`task web:check` tests catalog completeness, placeholders, English fallback and
locale route selection alongside request behavior. `task pages-test` checks the
actual rendered pages and links. Review every locale in the packaged studio,
including a language change during a real job. Verify keyboard help, narrow
layouts, playback, persistence, translated README navigation and the technical
document fallback. Rebuild the embedded gzip with `task web:build` after changes.
