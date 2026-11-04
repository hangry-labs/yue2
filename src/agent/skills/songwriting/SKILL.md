---
name: yue2-music
description: Use YuE2's MCP music tools, write complete songs from a brief, arrange supplied lyrics, and describe musical styles and instrumentation.
metadata:
  version: "6"
---

# YuE2 music skill

Retrieve `skill` before writing or preparing lyrics or using the other music
tools. Read it once in the current conversation; retrieve it again if its
one-hour `guide_token` expires. Copy that actual token into `generate_song`.
A successful `skill` result means retrieval is complete. Keep its token and
continue with writing or generation; do not call `skill` again for each step.

## Understand the request

- A theme, story, mood or idea: write original lyrics yourself. The user does
  not have to supply them. Develop their idea rather than singing their prose
  instructions literally.
- Partial lyrics or a hook: build a complete song around them, keeping any
  words the user says must stay.
- Finished lyrics: add appropriate section labels and line breaks if useful.
  Preserve the sung wording unless changes are requested or permitted.
  When asked only to label supplied lyrics, add only labels/line breaks: do not
  insert extra words, ad-libs or parenthetical production notes around them.
- Instrumental music: use `lyrics: ""` and an instrumental style description.
- Lyrics only: write the lyrics after reading this skill, without generating
  audio. When asked to make a song, proceed through the generation tools.

## Write a complete song

Normally plan for **two to four minutes**, with about **two and a half minutes**
as a useful starting point when the user gives no length. Develop a complete
musical and lyrical arc. Fit the amount of writing to the genre, phrasing,
repetitions and instrumental space; there is no required word count.

Choose a clear subject and a memorable hook. Use verses to develop images,
action or a story; let the chorus carry the central idea. Pay attention to
rhythm, stress, breathing points, natural rhymes and words that work when sung.
Repetition, chantable hooks, playful syllables and call-and-response can suit
an energetic song; a reflective song may use a different approach. Follow the
user's intent rather than imposing a particular mood, genre or vocal style.

The **lyrics provide the sequence and structure**. Useful labels include
`[Intro]`, `[Verse 1]`, `[Verse 2]`, `[Pre-Chorus]`, `[Chorus]`, `[Bridge]`,
`[Interlude]`, `[Final Chorus]` and `[Outro]`. Put section labels on separate
lines. One possible form is verse, pre-chorus, chorus, second verse, pre-chorus,
chorus, bridge and final chorus; use another form when the brief calls for it.

Include `[Intro]` when an opening section is wanted. Otherwise start with the
first verse or sung lines. Use interludes, a bridge and an outro where they
serve the song. These are structural hints to a generative model, not a
timestamped sequencer or a guarantee of the exact vocal entrance.

Write repeated chorus words out at each occurrence, rather than "repeat
chorus", "x2" or "same as above". Sung ad-libs such as `(hey!)`, `(oh-oh)` or
`(BONK!)` belong in the lyrics when wanted. Keep the title, API explanations,
Markdown fences and the user's prose brief out of the submitted lyric string.
Never shorten a supplied full song merely to fit a test excerpt.

## Describe the musical style

The API field is named **`direction`**, and it contains the **style description**
passed to YuE2. The section-by-section song form belongs in the lyrics.

Style is free text, not a fixed genre or instrument menu. Possibilities to
describe include:

- **Genre and influences:** synth-rock, electronic pop, J-pop rock ballad,
  country pop, cyberpunk pop, metal, folk, jazz, techno, or a deliberate blend.
- **Mood and energy:** cinematic, emotional, celebratory, dark, futuristic,
  playful horror-comedy, nostalgic or energetic.
- **Instruments and textures:** acoustic strumming, clean or distorted electric
  guitars, pedal steel, melodic or deep bass, analog synths, arpeggios, piano,
  strings, violin, cello, flute, saxophone, live drums or electronic percussion.
  A flute can be requested as a prominent melodic voice, an airy texture or
  part of the instrumental palette; it is not restricted to one genre.
- **Vocals:** male or female lead, sweet, bright, warm, breathy, gritty or
  expressive delivery; solo singing, layered harmonies, backing or gang vocals,
  chantable hooks and call-and-response. Specify the language where useful.
- **Feel and production:** driving or relaxed rhythm, approximate BPM, live
  instrumentation, electronic textures, sparse or dense instrumentation,
  straight or swung feel, major/minor tonal character, clean or gritty mix,
  wide stereo presentation, glossy modern production.

Select the details that matter to the user. Hybrid styles and contrasting
instruments are valid requests; do not flatten them into a generic acoustic
song. These are text-conditioning possibilities, not switches that guarantee
an instrument, production property or specific singer identity.

For example, a style can combine cinematic synth-rock, emotional female lead,
analog synthesizers, electric guitars, deep bass and punchy electronic drums.
Another can combine country-pop and cyberpunk, male harmonies, acoustic guitar,
pedal steel, synth leads and sidechained bass. A folk or cinematic style could
instead feature a breathy flute melody, strings and hand percussion. These
illustrate choices, not defaults or preferred styles.

`tempo_bpm` optionally adds a BPM hint to the style. It does not enforce a
metronome or change playback speed. Avoid promising exact notes, timings,
cloned voices, isolated vocals or stems: this interface produces a mixed
stereo song. The upstream model card lists English and Chinese; other
languages have local examples and remain experimental rather than equivalent
support guarantees.

## Use the tools

1. Retrieve `skill` if it has not been read in this conversation.
2. Call `generate_song` with `guide_token`, `lyrics`, `direction` and optional
   `duration_seconds`, `tempo_bpm`, `format`. Use those exact argument names;
   `style`, `prompt`, `text` and `duration` are not aliases. Lyrics is one string
   with line breaks, not an array of sections.
3. Keep the returned `job_id`. Wait for `poll_after_seconds` before the first
   `get_song` call and between later checks. The service recommends **30 seconds**.
   Avoid rapid polling to save API calls.
   `queued` and `generating` are ordinary progress states; keep
   checking rather than submitting the same song again. Handle failure or
   cancellation honestly. The service has one serial generation queue.
   Three polls are not a failure threshold: long songs or queue delays can need
   more checks. Continue while the job is pending; if you cannot keep waiting,
   retain its handle and report it as pending rather than failed or resubmitting.
4. On `complete`, return the **exact HTTP URL** provided by the tool. Mention
   its expiry and include the prepared lyrics if requested. Do not invent a
   download URL or claim to have listened to metadata. Use `cancel_song` with
   that job's handle when the user wants it stopped.

`duration_seconds` is a **ceiling, not a target**: it limits generation but does
not make a short set of lyrics fill that time. Song length depends on the amount
of lyrics, phrasing, repetitions, tempo and the generated arrangement. Increasing
the ceiling alone does not pad or extend a short song. When writing a longer
vocal song, develop enough verses, written-out chorus repetitions and a bridge
to support it. Preserve supplied lyrics unless changes are requested or permitted;
explain this limitation rather than silently adding words. Exact length is not
guaranteed, including for instrumentals.

The ceiling accepts 10-360 seconds; MCP defaults to **300 seconds (five minutes)**.
Normally **omit `duration_seconds`** and keep this default. It gives the song room
to finish; it is not a request to write or generate five minutes of material.
Do not add lyrics, repeats or instrumental sections just to fill the ceiling.
Override it only when the user specifically requests a duration constraint or
range. A smaller ceiling can cut a song off, and this control cannot enforce a
minimum or an exact duration. Each request starts a fresh composition.

Choose `opus` for compact listening/sharing (the default) or `flac` for lossless
editing; both are 48 kHz stereo. Only the selected file is stored. Audio bytes
are never returned inside MCP results. The download link lasts **one hour
after completion**; save the file before expiry. Anyone holding the link can
download it. Persisted output keeps completed links across server restarts,
with their original expiry; in-flight jobs and guide tokens do not survive.

The tools cannot alter server settings, models, adapters, seeds, sampling,
quality steps or model residency. Do not invent arguments or use another API
to bypass those limits. A tool error is not a successful song.

## Evidence and scope

The [upstream model card](https://huggingface.co/m-a-p/YuE2-3B) separates style,
lyrics and symbolic planning. Its [full-song example](https://huggingface.co/m-a-p/YuE2-3B/blob/main/examples/tonight-awake.json)
uses structured sections. The [official demo catalog](https://github.com/map-yue2/map-yue2.github.io/blob/main/data/cases.js)
includes varied genres and instrument descriptions, including flute, strings
and saxophone. The instrument/production vocabulary above also reflects the
project owner's supplied style examples. Requests remain generative guidance;
this skill does not certify the sound or limit the user's taste.
