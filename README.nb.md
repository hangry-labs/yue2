<p align="center"><img src="web/src/assets/yue2_logo_horizontal.webp" alt="Hangry Labs YuE2" width="900"></p>

<p align="center"><a href="README.md">English</a> · <strong>Norsk bokmål</strong> · <a href="README.pl.md">Polski</a> · <a href="README.ja.md">日本語</a> · <a href="README.zh.md">简体中文</a> · <a href="README.es.md">Español</a></p>

<p align="center"><a href="https://hangry-labs.github.io/yue2/examples/?lang=nb"><strong>🎧 Lytt til genererte sanger</strong></a></p>

# Hangry Labs YuE2

Utviklingsversjon **v0.1.0-snapshot**. Se [versjonshistorikken](#version-history).

Lag sanger lokalt fra sangtekst og musikalsk retning. Én Docker-container gir
deg et nettleserstudio, HTTP-API-er, MCP og 48 kHz stereolyd. Prosjektet bygger
på [yue2.cpp](https://github.com/ServeurpersoCom/yue2.cpp), C++20 og GGML.

<a id="quick-start"></a>

## Kom raskt i gang

Du trenger Docker med NVIDIA-GPU-støtte og en driver som passer CUDA 12.9.1.
Testmaskinen har **RTX 5070 Ti med 16 GB VRAM**. Andre GPU-er er ikke kvalifisert.
Last ned [de to modellfilene](#model-downloads) én gang til `data/models/`, og kjør
én av disse kommandoene fra mappen som inneholder `data/`.

**Bash:**

```bash
docker run -d --name yue2 --restart unless-stopped --gpus all -p 127.0.0.1:8087:8087 --mount "type=bind,source=$(pwd)/data/models,target=/models,readonly" --mount type=volume,source=yue2-output,target=/output hangrylabs/yue2:latest
```

**PowerShell:**

```powershell
docker run -d --name yue2 --restart unless-stopped --gpus all -p 127.0.0.1:8087:8087 --mount "type=bind,source=$($PWD.Path)\data\models,target=/models,readonly" --mount type=volume,source=yue2-output,target=/output hangrylabs/yue2:latest
```

Åpne **[http://localhost:8087](http://localhost:8087)**, skriv sangtekst og
musikalsk retning, og velg **Generer sang**. Du trenger ikke Python eller
kompilator på vertsmaskinen. `latest` er en rullerende utviklingsversjon.
Samme bilde finnes som `ghcr.io/hangry-labs/yue2:latest`.

<details markdown="1">
<summary><strong>Første gang: last ned modellene</strong></summary>

<a id="model-downloads"></a>

Opprett `data/models/` og behold filnavnene. Nedlastingene er omtrent 4,34 GB.

| Modell | Bruk | Størrelse |
| --- | --- | --- |
| [YuE2-3B-Q8_0.gguf](https://huggingface.co/Serveurperso/YuE2-GGUF/resolve/e630f2b8f6aedf8254c3186438633c1b5eeaf80a/YuE2-3B-Q8_0.gguf) | Sanggenerering | 3,81 GB |
| [YuE2-Vae-F32.gguf](https://huggingface.co/Serveurperso/YuE2-GGUF/resolve/e630f2b8f6aedf8254c3186438633c1b5eeaf80a/YuE2-Vae-F32.gguf) | Lydkoding og dekoding | 530 MB |

[Modellmanifestet](docker/models.json) inneholder SHA-256-sjekksummer.
I en kildekodeutsjekking kan `task models` laste ned og kontrollere filene.
Vekter pakkes ikke i bildet og lastes ikke ned av serveren. Når bilde og modeller
er på plass, kan generering kjøre uten nett. Modellvilkårene gjelder separat.

</details>

## Dette får du

- Sanggenerering fra stil og tekst, med full notasjon, bare melodi eller uten notasjon.
- Opus, MP3, Ogg, FLAC, WAV og AAC/M4A i stereo ved 48 kHz.
- Nettleserbibliotek med søk, favoritter, avspilling og gjenbruk av instruksjoner.
- Redigerbar ABC-notasjon, replay fra semantiske koder og fortsettelse fra en kilde.
- Én til tre lydvarianter av samme komposisjon; to som standard.
- Lokale LoRA-adaptere og VAE-koding/dekoding av lyd og latenter.
- Asynkrone jobber, avbryting, køgrenser og lagring på et varig volum.
- Modellstatus, kø, lagringsbruk og NVIDIA-GPU-diagrammer i System.
- HTTP-API-er, OpenAI-kompatibel klienttilgang og MCP-verktøy for agenter.

Transkripsjon og lydtokenisering krever valgfrie modeller og egne serverargumenter.
De er ikke del av standardnedlastingen. Se [modellveiledningen](docs/MODELS.md).

## Nettleserstudio

<p align="center"><a href="assets/screenshots/create-ui.webp"><img src="assets/screenshots/create-ui.webp" alt="YuE2-studioet for sangkomposisjon" width="1200"></a></p>

Velg engelsk, norsk bokmål, polsk, japansk, forenklet kinesisk eller spansk i
toppfeltet. Nettleseren husker valget. Direkte ruter er `/en`, `/nb`, `/pl`,
`/ja`, `/zh` og `/es`. Bytte av språk beholder tekst, innstillinger og aktive jobber.
Grensesnittspråk velger ikke sangspråk og oversetter ikke sangteksten.

**Ny sang** komponerer fra gjeldende tekst og retning hver gang. **Bruk ABC-notasjon**
beholder en angitt melodi. Replay gjenskaper en eksisterende fremføring;
tekstendringer kan ikke endre sangen som allerede ligger i lydkodene.
Beskriv sjanger, instrumenter, stemning og stemme i musikalsk retning; bruk
etiketter som `[Verse]` og `[Chorus]` i sangteksten. Dette er modellhint.

## API-er og agenter

Bruk `/v1/audio/music` for en ferdig lydfil eller `/v1/audio/speech` med en
OpenAI-klient. Begge genererer musikk, ikke vanlig tale. `/v1/models` viser modellen.

```bash
curl --fail-with-body http://localhost:8087/v1/audio/music -H 'Content-Type: application/json' --data '{"model":"yue2","lyrics":"[Verse]\nMorning light across the floor","style":"English acoustic pop, warm singing","duration":30,"steps":8,"response_format":"opus"}' --output song.opus
```

Det native `/synth`-API-et returnerer en jobb-ID. Sjekk `/job?id=JOB_ID` til status
er `done`, og hent `/job?id=JOB_ID&result=1` for multipart med lyd, replay-JSON og
latenter. [API-veiledningen](docs/API.md) og [OpenAPI](http://localhost:8087/openapi.json)
beskriver kontrakten. [Den lokale API-visningen](http://localhost:8087/docs) virker offline.

Koble MCP-klienten til `http://localhost:8087/mcp` med Streamable HTTP.
Verktøyene er `skill`, `generate_song`, `get_song` og `cancel_song`. Agenten leser
først ferdigheten, skriver eller klargjør en hel sang og mottar en HTTP-lenke
som varer én time. Agenten kan ikke endre avanserte kjøretidsinnstillinger.
Se [MCP-veiledningen](docs/MCP.md).

## Standardverdier og lagring

Standard er **8 trinn**, tilfeldig frø, **24 576** konteksttokener og to
lydvarianter. Musikk-/tale-API-ene og MCP gir én variant per kall. Varighet er en
øvre grense, ikke en garanti. Vanlig oppstart frigjør modellvekter mellom trinnene.
Kun CUDA distribueres som støttet GPU-oppsett.

Alle genereringsruter deler én seriell arbeider og maksimalt åtte godtatte jobber.
Full kø gir HTTP 429 med `Retry-After`; klienten må vente før nytt forsøk.
`/health`, `/status` og `/system/queue` viser driftsstatus.
`YUE2_API_KEY` beskytter `/v1` og `/mcp` når satt; Studio/native-ruter beholder
sin lokale tilgang. Standardkommandoen binder bare til localhost.

Modellene ligger på verten. `yue2-output` bevarer ferdige serverresultater og
MCP-filer ved containerbytte. Native resultater varer normalt 24 timer; agentlenker
én time. Nettleserbiblioteket lagres separat i IndexedDB. Last ned viktige sanger;
modellmappen sikkerhetskopierer ikke nettleseren. Se [kø og lagring](docs/QUEUE.md).

## Dokumentasjon og utvikling

[Dokumentasjonsoversikt](docs/README.nb.md) · [Docker](docs/DOCKER.md) ·
[lydformater](docs/AUDIO.md) · [utvikling](docs/DEVELOPMENT.md) ·
[byggavhengigheter](docs/BUILDING.md) · [benchmark](docs/BENCHMARKS.md).
De detaljerte tekniske referansene er på engelsk med tydelig språkfallback på nettstedet.

Med en utsjekking, Docker, Python og Task: `task models`, `task build`, `task start`.
`task validate` kontrollerer verktøy, UI og native CPU-kode. `task test1` kjører
den faste GPU-baselinen. Nettsidevisning: `task pages`; stopp med `task pages-stop`.
Benchmarkene skiller kald oppstart, varm generering, VRAM og ASR som en usikker
trendindikator. De er ikke garantier for alle GPU-er eller sanger.

## Personvern, opphav og lisens

Genereringen skjer på maskinen din. Nedlasting kontakter modellvert og registre;
UI-et trenger ingen CDN. Bruk materiale du har rett til å behandle og del ansvarlig.
Eksterne produktintegrasjoner håndteres separat; det finnes ingen innebygd kobling her.

[MAP](https://huggingface.co/m-a-p/YuE2-3B) leverer YuE2 og lydmodellen,
[yue2.cpp](https://github.com/ServeurpersoCom/yue2.cpp) den native motoren.
Hangry Labs vedlikeholder UI, API-er, pakking og validering. Prosjektkoden er
[MIT-lisensiert](LICENSE). Modellene har egne ikke-kommersielle vilkår;
se [modellkilder](docs/MODELS.md) og [tredjepartsmerknader](THIRD_PARTY_NOTICES.md).
Kontakt: [contact@hangrylabs.app](mailto:contact@hangrylabs.app).

<a id="version-history"></a>
<details markdown="1">
<summary><strong>Versjonshistorikk</strong></summary>

### v0.1.0-snapshot

Utviklingsversjon med lokalt studio, native/OpenAI-kompatible API-er, MCP,
flerspråklig grensesnitt, eksterne modeller og verifiserte CUDA-avhengigheter.
En stabil programutgivelse er ennå ikke publisert.

</details>
