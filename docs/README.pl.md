---
layout: default
title: Dokumentacja
lang: pl
permalink: /docs/pl/
---
# Dokumentacja

[English](README.md) · [Norsk bokmål](README.nb.md) · **Polski** · [日本語](README.ja.md) · [简体中文](README.zh.md) · [Español](README.es.md)

Zacznij od [szybkiego startu](../README.pl.md#quick-start): pobierz raz dwa modele,
a następnie uruchom kontener CUDA jedną komendą Dockera.

## Od tekstu do piosenki

Otwórz studio na `http://localhost:8087`. W **Tekście piosenki** podaj słowa do
zaśpiewania. W **Opisie muzycznym** określ gatunek, instrumenty, język i głos.
`[Verse]` i `[Chorus]` opisują strukturę. Nowa piosenka tworzy świeżą kompozycję;
partytura ABC i odtworzenie kodów są świadomym wyborem ponownego użycia melodii
lub wykonania. Język interfejsu nigdy nie tłumaczy Twoich słów.

Domyślnie używane jest 8 kroków i dwa warianty brzmienia; można wybrać od jednego
do trzech. Czas to górny limit. Pobieraj utwory, które chcesz zachować.
Biblioteka przeglądarki i wolumin wyników serwera to oddzielne magazyny.

## API i MCP

`POST /v1/audio/music` lub `/v1/audio/speech` zwraca jeden gotowy plik.
`POST /synth` zwraca zadanie sprawdzane przez `/job?id=JOB_ID`.
Lokalne `/docs` i `/openapi.json` opisują kontrakty. MCP działa przez Streamable
HTTP pod `/mcp`: najpierw `skill`, potem `generate_song`, sprawdzanie `get_song`
i anulowanie `cancel_song`. Gotowe odnośniki są ważne godzinę.

## Szczegółowe przewodniki

Referencje techniczne poniżej są po angielsku. Witryna zachowuje wybór języka
i wyraźnie oznacza dokumenty, które nie mają jeszcze tłumaczenia.

| Przewodnik | Zakres |
| --- | --- |
| [Docker](DOCKER.md) | Uruchamianie, GPU, woluminy i sieć |
| [Modele](MODELS.md) | Pobieranie, sumy kontrolne i modele opcjonalne |
| [Formaty audio](AUDIO.md) | Import oraz eksport stratny i bezstratny |
| [API](API.md) | Zgodność z OpenAI, zadania i uwierzytelnianie |
| [MCP](MCP.md) | Narzędzia, instrukcja, ograniczenia agentów i linki |
| [Kolejka i wyniki](QUEUE.md) | Pojemność, anulowanie, HTTP 429 i trwałe wyniki |
| [Adaptery](ADAPTERS.md) | Lokalne pliki LoRA i ich siła |
| [Silnik](ARCHITECTURE.md) | ABC, pola żądań i narzędzia natywne |
| [Rozwój](DEVELOPMENT.md) | Task, struktura repozytorium i dane |
| [Budowanie](BUILDING.md) | Zweryfikowane zależności CUDA i powrót do starszej wersji |
| [Benchmarki](BENCHMARKS.md) | Czas, VRAM i ograniczenia ocen ASR |
| [Witryna](WEBSITE.md) | Podgląd i publikacja strony |
| [Wydania](RELEASING.md) | Wersje, rejestry i walidacja |

Warunki modeli są oddzielne od licencji aplikacji. Zobacz [MIT](../LICENSE)
i [informacje o zależnościach](../THIRD_PARTY_NOTICES.md).
