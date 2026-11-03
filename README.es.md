<p align="center"><img src="web/src/assets/yue2_logo_horizontal.webp" alt="Hangry Labs YuE2" width="900"></p>

<p align="center"><a href="README.md">English</a> · <a href="README.nb.md">Norsk bokmål</a> · <a href="README.pl.md">Polski</a> · <a href="README.ja.md">日本語</a> · <a href="README.zh.md">简体中文</a> · <strong>Español</strong></p>

<p align="center"><a href="https://hangry-labs.github.io/yue2/examples/?lang=es"><strong>🎧 Escuchar canciones generadas</strong></a></p>

# Hangry Labs YuE2

Versión **v1.0.0**. Consulta el [historial](#version-history).

Genera canciones en tu GPU a partir de letras y una dirección musical. Un único
contenedor Docker ofrece estudio en el navegador, API HTTP, MCP y audio estéreo
a 48 kHz. Se basa en [yue2.cpp](https://github.com/ServeurpersoCom/yue2.cpp), C++20 y GGML.

<a id="quick-start"></a>

## Inicio rápido

Necesitas Docker con soporte para GPU NVIDIA y un controlador compatible con
CUDA 12.9.1. El equipo probado tiene **RTX 5070 Ti con 16 GB de VRAM**; otras
configuraciones no están verificadas. Descarga una vez [los dos modelos](#model-downloads)
en `data/models/`. Desde el directorio que contiene `data/`, ejecuta una de estas líneas:

**Bash:**

```bash
docker run -d --name yue2 --restart unless-stopped --gpus all -p 127.0.0.1:8087:8087 --mount "type=bind,source=$(pwd)/data/models,target=/models,readonly" --mount type=volume,source=yue2-output,target=/output hangrylabs/yue2:latest
```

**PowerShell:**

```powershell
docker run -d --name yue2 --restart unless-stopped --gpus all -p 127.0.0.1:8087:8087 --mount "type=bind,source=$($PWD.Path)\data\models,target=/models,readonly" --mount type=volume,source=yue2-output,target=/output hangrylabs/yue2:latest
```

Abre **[http://localhost:8087](http://localhost:8087)**, escribe la letra y el estilo,
y pulsa **Generar canción**. No necesitas Python ni compilador en el equipo.
`latest` es una etiqueta móvil de desarrollo. El mismo contenedor está disponible
en `ghcr.io/hangry-labs/yue2:latest`.

<details markdown="1">
<summary><strong>Primera ejecución: descargar los modelos</strong></summary>

<a id="model-downloads"></a>

Crea `data/models/` y conserva los nombres originales. La descarga total es de unos 4,34 GB.

| Modelo | Uso | Tamaño |
| --- | --- | --- |
| [YuE2-3B-Q8_0.gguf](https://huggingface.co/Serveurperso/YuE2-GGUF/resolve/e630f2b8f6aedf8254c3186438633c1b5eeaf80a/YuE2-3B-Q8_0.gguf) | Generación de canciones | 3,81 GB |
| [YuE2-Vae-F32.gguf](https://huggingface.co/Serveurperso/YuE2-GGUF/resolve/e630f2b8f6aedf8254c3186438633c1b5eeaf80a/YuE2-Vae-F32.gguf) | Codificación y decodificación de audio | 530 MB |

El [manifiesto](docker/models.json) incluye sumas SHA-256. Desde una copia del
repositorio, `task models` descarga y verifica los archivos. Los pesos no van
dentro de la imagen y el servidor no los descarga. Una vez preparados, la
generación funciona sin conexión. Los modelos tienen condiciones independientes.

</details>

## Funciones

- Canciones a partir de estilo y letra, con partitura completa, solo melodía o sin partitura.
- Audio estéreo a 48 kHz en Opus, MP3, Ogg, FLAC, WAV y AAC/M4A.
- Biblioteca del navegador con búsqueda, favoritas, reproducción y reutilización de indicaciones.
- Partituras ABC editables, recreación con códigos semánticos y continuación desde una fuente.
- De una a tres versiones acústicas de la misma composición; dos por defecto.
- Adaptadores LoRA locales y conversión VAE entre audio y representaciones latentes.
- Trabajos asíncronos, cancelación, límites de cola y resultados en un volumen persistente.
- Estado de modelos, cola, almacenamiento y gráficos de GPU NVIDIA en Sistema.
- API HTTP nativa, clientes compatibles con OpenAI y herramientas MCP para agentes.

La transcripción y la tokenización de audio requieren modelos opcionales y
argumentos del servidor. No forman parte de la descarga predeterminada.
Consulta los [modelos](docs/MODELS.md).

## Estudio en el navegador

<p align="center"><a href="assets/screenshots/create-ui.webp"><img src="assets/screenshots/create-ui.webp" alt="Estudio YuE2 para componer canciones" width="1200"></a></p>

Elige inglés, noruego bokmål, polaco, japonés, chino simplificado o español en
la cabecera. El navegador recuerda la elección. Las rutas directas son `/en`,
`/nb`, `/pl`, `/ja`, `/zh` y `/es`. Cambiar el idioma conserva la letra, los ajustes
y el trabajo activo. El idioma de la interfaz no selecciona el del canto ni traduce la letra.

**Nueva canción** compone de nuevo con la letra y dirección actuales.
**Usar partitura ABC** conserva una melodía especificada. Recrear códigos usa una
interpretación existente: editar la letra no reescribe el canto ya presente en
los códigos. Describe género, instrumentos, ambiente y voz en dirección musical;
usa `[Verse]` y `[Chorus]` para la estructura en la letra. Son pistas para el modelo.

## API y agentes

`/v1/audio/music` devuelve un archivo terminado. `/v1/audio/speech` permite usar
clientes OpenAI, pero también genera música, no narración hablada.
`/v1/models` proporciona información del modelo.

```bash
curl --fail-with-body http://localhost:8087/v1/audio/music -H 'Content-Type: application/json' --data '{"model":"yue2","lyrics":"[Verse]\nMorning light across the floor","style":"English acoustic pop, warm singing","duration":30,"steps":8,"response_format":"opus"}' --output song.opus
```

La ruta nativa `/synth` devuelve un identificador. Consulta `/job?id=JOB_ID` hasta
`done` y descarga `/job?id=JOB_ID&result=1`, un multipart con audio, JSON de
recreación y latentes. Consulta la [guía API](docs/API.md), la
[documentación local](http://localhost:8087/docs) y el [esquema OpenAPI](http://localhost:8087/openapi.json).

Conecta MCP por Streamable HTTP a `http://localhost:8087/mcp`.
Las herramientas son `skill`, `generate_song`, `get_song` y `cancel_song`.
El agente primero lee la guía, escribe o prepara una canción completa y obtiene
un enlace HTTP válido durante una hora. No puede cambiar ajustes avanzados del
entorno. Consulta la [guía MCP](docs/MCP.md).

## Valores predeterminados y almacenamiento

Se usan **8 pasos**, semillas aleatorias, contexto de **24 576 tokens** y dos
variantes. Las rutas compatibles y MCP devuelven una por llamada. La duración es
un límite superior; la canción puede terminar antes. El inicio normal libera
los pesos entre etapas. La distribución GPU soportada utiliza solo CUDA.

Todas las rutas comparten un trabajador secuencial y ocho plazas, incluida la
activa. Una cola llena responde HTTP 429 con `Retry-After`; espera antes de
reintentar. `/health`, `/status` y `/system/queue` muestran el estado.
`YUE2_API_KEY` protege `/v1` y `/mcp` si se configura. Studio y las rutas nativas
mantienen su acceso local. La orden inicial solo expone el puerto en localhost.

Los modelos permanecen en el equipo. `yue2-output` conserva los resultados
terminados al sustituir el contenedor. Los resultados nativos duran 24 horas
por defecto y los enlaces de agentes una hora. La biblioteca IndexedDB es
independiente. Descarga las canciones importantes; la carpeta de modelos no
respalda la biblioteca del navegador. Consulta [cola y almacenamiento](docs/QUEUE.md).

## Documentación y desarrollo

[Índice de documentación](docs/README.es.md) · [Docker](docs/DOCKER.md) ·
[formatos](docs/AUDIO.md) · [desarrollo](docs/DEVELOPMENT.md) ·
[dependencias de compilación](docs/BUILDING.md) · [pruebas de rendimiento](docs/BENCHMARKS.md).
Las referencias técnicas detalladas están en inglés; el sitio indica claramente
cuando no existe una traducción.

Con el repositorio, Docker, Python y Task: `task models`, `task build`, `task start`.
`task validate` comprueba herramientas, UI y código nativo CPU. `task test1`
ejecuta la referencia GPU fija. `task pages` abre la vista previa del sitio;
`task pages-stop` la detiene. Las mediciones separan inicio en frío, generación
en caliente y VRAM. ASR es un indicador imperfecto de tendencias, no un juez musical.

## Privacidad, atribución y licencias

La generación ocurre en tu equipo. Las descargas contactan con registros y
el servidor de modelos; la interfaz no necesita CDN. Usa material que tengas
derecho a procesar y comparte con responsabilidad. Las integraciones externas
se gestionan por separado.

[MAP](https://huggingface.co/m-a-p/YuE2-3B) proporciona los modelos y
[yue2.cpp](https://github.com/ServeurpersoCom/yue2.cpp) el motor nativo.
Hangry Labs mantiene UI, API, empaquetado y validación. El código del proyecto
usa [MIT](LICENSE); los modelos tienen condiciones no comerciales independientes.
Consulta [procedencia de modelos](docs/MODELS.md) y [avisos de terceros](THIRD_PARTY_NOTICES.md).
Contacto: [contact@hangrylabs.app](mailto:contact@hangrylabs.app).

<a id="version-history"></a>
<details markdown="1">
<summary><strong>Historial de versiones</strong></summary>

### v1.0.0

Primera versión estable con estudio local, API nativa y compatible con OpenAI, MCP,
interfaz multilingüe, modelos externos y dependencias CUDA verificadas.
Preparada para su publicación. Las imágenes con versión estarán disponibles
tras publicarse; el inicio rápido utiliza la etiqueta actualizable `latest`.

</details>
