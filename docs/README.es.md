---
layout: default
title: Documentación
lang: es
permalink: /docs/es/
---
# Documentación

[English](README.md) · [Norsk bokmål](README.nb.md) · [Polski](README.pl.md) · [日本語](README.ja.md) · [简体中文](README.zh.md) · **Español**

Empieza por el [inicio rápido](../README.es.md#quick-start): descarga los dos
modelos una vez y arranca el contenedor CUDA con una sola orden Docker.

## De la letra a la canción

Abre `http://localhost:8087`. Pon las palabras que se cantarán en **Letra** y el
género, instrumentos, idioma y voz en **Dirección musical**. `[Verse]` y
`[Chorus]` describen la estructura. Nueva canción compone de nuevo; la partitura
ABC y la recreación de códigos reutilizan una melodía o interpretación de forma
explícita. El idioma de la interfaz nunca traduce tus letras.

Se usan 8 pasos y dos variantes por defecto; puedes elegir de una a tres.
La duración es un límite superior. Descarga las canciones que quieras conservar.
La biblioteca del navegador y el volumen de resultados del servidor son independientes.

## API y MCP

`POST /v1/audio/music` o `/v1/audio/speech` devuelve un archivo completo.
`POST /synth` crea un trabajo que consultas con `/job?id=JOB_ID`.
Los contratos están en `/docs` y `/openapi.json` del servidor local.
MCP usa Streamable HTTP en `/mcp`: primero `skill`, luego `generate_song`,
consulta `get_song` y cancela con `cancel_song`. Los enlaces duran una hora.

## Guías detalladas

Las referencias técnicas siguientes están en inglés. El sitio conserva tu
idioma e indica claramente cuando el documento no tiene traducción.

| Guía | Contenido |
| --- | --- |
| [Docker](DOCKER.md) | Inicio, GPU, volúmenes y red |
| [Modelos](MODELS.md) | Descargas, sumas y componentes opcionales |
| [Audio](AUDIO.md) | Importación y exportación con o sin pérdidas |
| [API](API.md) | Compatibilidad OpenAI, trabajos y autenticación |
| [MCP](MCP.md) | Herramientas, habilidad, límites y enlaces |
| [Cola y resultados](QUEUE.md) | Capacidad, cancelación, HTTP 429 y persistencia |
| [Adaptadores](ADAPTERS.md) | Archivos LoRA locales e intensidad |
| [Motor](ARCHITECTURE.md) | ABC, campos y herramientas nativas |
| [Desarrollo](DEVELOPMENT.md) | Task, estructura y datos locales |
| [Compilación](BUILDING.md) | Dependencias CUDA verificadas y reversión |
| [Rendimiento](BENCHMARKS.md) | Tiempo, VRAM y limitaciones del análisis ASR |
| [Sitio web](WEBSITE.md) | Vista previa y publicación |
| [Versiones](RELEASING.md) | Versionado, registros y validación |

Las condiciones de modelos y aplicación son independientes. Consulta la
[licencia MIT](../LICENSE) y los [avisos de terceros](../THIRD_PARTY_NOTICES.md).
