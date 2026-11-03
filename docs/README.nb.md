---
layout: default
title: Dokumentasjon
lang: nb
permalink: /docs/nb/
---
# Dokumentasjon

[English](README.md) · **Norsk bokmål** · [Polski](README.pl.md) · [日本語](README.ja.md) · [简体中文](README.zh.md) · [Español](README.es.md)

Start med [hurtigstarten](../README.nb.md#quick-start): last ned de to modellene
én gang og start CUDA-containeren med én Docker-kommando.

## Fra tekst til sang

Åpne studioet på `http://localhost:8087`. Skriv ordene som skal synges i
**Sangtekst**, og sjanger, instrumenter, språk og vokaltype i **Musikalsk retning**.
`[Verse]`, `[Chorus]` og lignende beskriver formen. Ny sang lager en ny
komposisjon; ABC-notasjon og replay er eksplisitte valg for å gjenbruke en melodi
eller fremføring. Grensesnittspråket endrer aldri sangteksten.

Standard er 8 trinn og to lydvarianter. Du kan velge én til tre. Varighet er en
øvre grense; modellen kan avslutte tidligere. Last ned sanger du vil beholde.
Nettleserbiblioteket og serverens resultatvolum er to separate lagringssteder.

## API og MCP

`POST /v1/audio/music` eller `/v1/audio/speech` gir én ferdig lydfil.
`POST /synth` gir en jobb-ID som følges med `/job?id=JOB_ID`.
`/docs` og `/openapi.json` på den lokale serveren beskriver kontraktene.
MCP bruker Streamable HTTP på `/mcp`: hent `skill` først, bruk `generate_song`,
sjekk `get_song`, og avbryt med `cancel_song`. Ferdige lenker varer én time.

## Videre lesing

De detaljerte tekniske veiledningene nedenfor er på engelsk. Nettstedet beholder
språkvalget og viser en melding når selve dokumentet ikke er oversatt.

| Veiledning | Innhold |
| --- | --- |
| [Docker](DOCKER.md) | Oppstart, GPU, monteringer og nettverk |
| [Modeller](MODELS.md) | Nedlastinger, sjekksummer og valgfrie modeller |
| [Lydformater](AUDIO.md) | Import, tapsfri eksport og komprimerte formater |
| [API](API.md) | OpenAI-kompatibilitet, native jobber og autentisering |
| [MCP](MCP.md) | Verktøy, ferdighet, agentgrenser og lenker |
| [Kø og lagring](QUEUE.md) | Kapasitet, avbryting, HTTP 429 og varige resultater |
| [Adaptere](ADAPTERS.md) | Lokale LoRA-filer og styrke |
| [Motorreferanse](ARCHITECTURE.md) | ABC, forespørselsfelt og native verktøy |
| [Utvikling](DEVELOPMENT.md) | Task, struktur og lokal data |
| [Bygg](BUILDING.md) | Verifiserte CUDA-avhengigheter og rollback |
| [Benchmark](BENCHMARKS.md) | Tid, VRAM og begrensninger ved ASR-vurdering |
| [Nettside](WEBSITE.md) | Forhåndsvisning og publisering |
| [Utgivelser](RELEASING.md) | Versjoner, registre og validering |

Modellvilkår og programlisens er separate. Se [MIT](../LICENSE) og
[tredjepartsmerknader](../THIRD_PARTY_NOTICES.md).
