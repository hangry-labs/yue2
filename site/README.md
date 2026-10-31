# Website build support

The public README, technical Markdown and listening gallery use the local
Apache-2.0 theme in [theme/](theme/). `Dockerfile`, `Gemfile` and `Gemfile.lock`
pin the independent Pages preview builder, adapted from Faster Qwen3-TTS Studio.
They are excluded from the CUDA runtime image.

See [the website guide](../docs/WEBSITE.md) for build, preview, content routing,
validation and deployment. Start with `task pages`; stop with `task pages-stop`.
