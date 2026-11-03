---
layout: default
title: Documentation
permalink: /docs/
---
# Documentation

[English](README.md) · [Norsk bokmål](README.nb.md) · [Polski](README.pl.md) · [日本語](README.ja.md) · [简体中文](README.zh.md) · [Español](README.es.md)

The overview, documentation introductions and application are available in six
interface languages. Detailed technical references currently remain in English;
the website keeps your selected language and labels that fallback explicitly.

Start with the [project quick start](../README.md#quick-start) to run the CUDA
container with external models.

## Using YuE2

| Guide | Contents |
| --- | --- |
| [Song examples](../examples/README.md) | Listening gallery, original prompts, recipes and generation provenance |
| [Docker runtime](DOCKER.md) | Registry images, mounts, GPU selection, defaults and weight-free packaging |
| [Models](MODELS.md) | Pinned downloads, optional components, provenance and conversion |
| [Audio formats](AUDIO.md) | FFmpeg uploads, Opus/MP3/FLAC/AAC exports and native WAV |
| [Music and SDK APIs](API.md) | Music endpoint, OpenAI-compatible clients, schema, quality and access |
| [Queue and result storage](QUEUE.md) | Shared backlog limits, retries, status, volume retention and load tests |
| [Agent music tools](MCP.md) | MCP connection, songwriting skill, restricted controls and one-hour audio links |
| [LoRA adapters](ADAPTERS.md) | Supported adapter files, placement and loading |
| [Languages and localization](LOCALIZATION.md) | Studio locales, translated READMEs, gallery text and technical-reference fallback |
| [API and engine reference](ARCHITECTURE.md) | Request fields, job responses, CLI tools and engine internals |

## Developing And Maintaining

| Guide | Contents |
| --- | --- |
| [Development](DEVELOPMENT.md) | Repository layout, local data migration, Task commands and native builds |
| [Website](WEBSITE.md) | Themed README site, local preview, gallery integration and Pages deployment |
| [Build dependencies](BUILDING.md) | Reusable CUDA libraries, integrity checks and source rebuilds |
| [Benchmarks](BENCHMARKS.md) | Resident-model speed/VRAM/lyric suite and historical long-song baseline |
| [CI and releases](RELEASING.md) | Tags, registry publication and Docker Hub overview maintenance |
| [Docker Hub overview](dockerhub.md) | Registry-ready product description with absolute links |

The engine reference also contains inherited upstream performance/parity results.
The [benchmark guide](BENCHMARKS.md) records this fork's measured product baseline.

Application and dependency licenses are described in the root
[license](../LICENSE) and [third-party notices](../THIRD_PARTY_NOTICES.md).
