# Inspect music-agent calls

This manual test gives an OpenAI-compatible language model the **actual MCP tool
catalog and server instructions**. It retrieves the real `skill`, lets the model
write or prepare a complete song, and validates its proposed `generate_song`
arguments against the live JSON Schema and returned guide token.

**Default inspection does not submit generation, create a job, download audio
or call ASR.** It stops once a valid generation call has been inspected. The
model's tool arguments are recorded unchanged. This evaluates how the model
uses the API and prepares style/lyrics, rather than the generated performance.

Install the test-only MCP SDK and choose the model endpoint explicitly:

```bash
python -m pip install 'mcp>=2,<3'
task test:mcp-agent -- --model-url http://YOUR_MODEL_HOST:PORT
```

The direct command is
`python tests/agents/songwriting.py --model-url http://YOUR_MODEL_HOST:PORT`.
`YUE2_AGENT_MODEL_URL` can supply that URL instead; there is no assumed remote
endpoint. Model selection uses the first `/v1/models` entry unless `--model` is
given. Optional `YUE2_AGENT_MODEL_KEY` and `YUE2_API_KEY` go only into the model
and MCP HTTP Authorization headers respectively.

The seven synthetic cases cover a cinematic synth-rock song, prominent flute
instrumentation, supplied lyrics with a country/cyberpunk style, an anime ending
theme, a playful Halloween pop-rock song, a lyrics-only request and instrumental
techno. Fixtures request explicit song lengths, typically 150 seconds; the normal MCP
ceiling is 300 seconds when no duration is requested. Select cases
with repeated `--case ID` or supply another `--cases FILE`.

The checks inspect skill retrieval/order, valid argument names and types,
duration, requested section structure, preservation of supplied words/ad-libs
and style, specified instruments, and whether a lyrics-only request avoids an
audio call. They impose no word-count budget, taste preference or ASR score.
Pacing, rhyme and how well an original lyric develops the brief remain review
questions; JSON Schema does not certify songwriting quality.

## Optional generation test

Add **`--generate-audio`** only when end-to-end generation is wanted. This mode
forwards calls to the production MCP service, produces real songs, polls jobs
and downloads completed links. Ownership/idle/other-GPU-container guards run
before it starts. It uses the existing serial worker and does not change server
settings. The host waits at least 30 seconds after submission and between polls,
and cancels only
this test's unfinished jobs on cleanup. Those are host actions, not evidence
that the model implemented transport, timing or downloads itself.

## Results and limits

Traces, proposed lyrics/styles and a summary go under ignored
`data/results/mcp-agent/<timestamp>/`; explicit `--output` must name a new
directory. Only the opted-in generation mode saves audio. The trace includes
full model API responses and temporary guide/download capabilities; keep it as
local diagnostic data. The model receives synthetic prompts and the public
skill, without private project context or API keys.

`max_tokens` defaults to **100000 per response**, and requests explicitly set
`chat_template_kwargs.enable_thinking: true`. The model response timeout defaults
to 7200 seconds so a long reasoning response is not cut off at five minutes;
`--max-tokens` and `--model-timeout` can override those test settings. Other model
sampling settings remain at server defaults. `--max-turns` defaults to 8 for
inspection and 48 for optional generation. Inspection stops before
submitting the proposed song and does not test its eventual job status or sound.
Optional generation timing includes model calls, network and host waits and is
not a native inference benchmark. No arguments or results are silently repaired.
