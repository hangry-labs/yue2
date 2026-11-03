<p align="center"><img src="web/src/assets/yue2_logo_horizontal.webp" alt="Hangry Labs YuE2" width="900"></p>

<p align="center"><a href="README.md">English</a> · <a href="README.nb.md">Norsk bokmål</a> · <a href="README.pl.md">Polski</a> · <a href="README.ja.md">日本語</a> · <strong>简体中文</strong> · <a href="README.es.md">Español</a></p>

<p align="center"><a href="https://hangry-labs.github.io/yue2/examples/?lang=zh"><strong>🎧 收听生成的歌曲</strong></a></p>

# Hangry Labs YuE2

开发版本 **v0.1.0-snapshot**。参见[版本历史](#version-history)。

根据歌词和音乐风格描述，在自己的GPU上生成歌曲。一个Docker容器提供浏览器工作室、
HTTP API、MCP和48 kHz立体声输出。项目基于
[yue2.cpp](https://github.com/ServeurpersoCom/yue2.cpp)、C++20与GGML。

<a id="quick-start"></a>

## 快速开始

需要支持NVIDIA GPU的Docker及兼容CUDA 12.9.1的驱动。
已验证的设备为**16 GB显存的RTX 5070 Ti**，其他配置尚未验证。
首次使用时，将[两个模型文件](#model-downloads)下载到`data/models/`。
然后在包含`data/`的目录中，执行以下任意一条单行命令。

**Bash：**

```bash
docker run -d --name yue2 --restart unless-stopped --gpus all -p 127.0.0.1:8087:8087 --mount "type=bind,source=$(pwd)/data/models,target=/models,readonly" --mount type=volume,source=yue2-output,target=/output hangrylabs/yue2:latest
```

**PowerShell：**

```powershell
docker run -d --name yue2 --restart unless-stopped --gpus all -p 127.0.0.1:8087:8087 --mount "type=bind,source=$($PWD.Path)\data\models,target=/models,readonly" --mount type=volume,source=yue2-output,target=/output hangrylabs/yue2:latest
```

打开**[http://localhost:8087](http://localhost:8087)**，输入歌词与音乐风格，点击“生成歌曲”。
主机无需安装Python或编译器。`latest`为持续更新的开发标签。
相同镜像也可从`ghcr.io/hangry-labs/yue2:latest`获取。

<details markdown="1">
<summary><strong>首次使用：下载模型</strong></summary>

<a id="model-downloads"></a>

创建`data/models/`，并保持原始文件名。下载总量约4.34 GB。

| 模型 | 用途 | 大小 |
| --- | --- | --- |
| [YuE2-3B-Q8_0.gguf](https://huggingface.co/Serveurperso/YuE2-GGUF/resolve/e630f2b8f6aedf8254c3186438633c1b5eeaf80a/YuE2-3B-Q8_0.gguf) | 歌曲生成 | 3.81 GB |
| [YuE2-Vae-F32.gguf](https://huggingface.co/Serveurperso/YuE2-GGUF/resolve/e630f2b8f6aedf8254c3186438633c1b5eeaf80a/YuE2-Vae-F32.gguf) | 音频编码与解码 | 530 MB |

[模型清单](docker/models.json)包含SHA-256校验值。已检出源码时，可通过`task models`
下载并验证文件。权重不包含在镜像中，服务器也不会自动下载。
镜像与模型就绪后，可离线生成。模型使用条款与应用许可分开适用。

</details>

## 功能概览

- 根据风格和歌词生成歌曲，支持完整乐谱、仅旋律或不使用乐谱的模式。
- 输出48 kHz立体声Opus、MP3、Ogg、FLAC、WAV及AAC/M4A。
- 浏览器曲库支持搜索、收藏、播放和复用提示。
- 可编辑ABC乐谱，通过语义编码重放，或从源片段继续生成。
- 同一作曲可生成1至3个声音版本，默认2个。
- 支持本地LoRA适配器，以及音频与潜在表示的VAE编码／解码。
- 异步任务、取消、队列上限及持久卷结果存储。
- 系统页面显示模型状态、队列、存储用量与NVIDIA GPU图表。
- 原生HTTP API、OpenAI兼容客户端接口，以及供智能体使用的MCP工具。

乐谱转录和音频分词需要额外模型与服务器参数，不在默认下载范围内。
详情见[模型指南](docs/MODELS.md)。

## 浏览器工作室

<p align="center"><a href="assets/screenshots/create-ui.webp"><img src="assets/screenshots/create-ui.webp" alt="YuE2歌曲创作工作室" width="1200"></a></p>

在页眉选择英语、挪威语书面语、波兰语、日语、简体中文或西班牙语。
浏览器会记住选择，也可直接访问`/en`、`/nb`、`/pl`、`/ja`、`/zh`或`/es`。
切换语言会保留歌词、设置与活动任务。界面语言不决定演唱语言，也不会翻译歌词。

“新建歌曲”每次点击都根据当前歌词和风格重新作曲。“使用ABC乐谱”保留指定旋律。
重放音频编码会重新渲染已有演出，因此编辑歌词无法改写编码中已包含的演唱。
曲风、乐器、情绪和声线写在音乐风格描述中，`[Verse]`、`[Chorus]`等结构标签放在歌词中。
这些描述属于模型提示，并非严格控制保证。

## API与智能体

`/v1/audio/music`直接返回完整音频。OpenAI客户端可以使用`/v1/audio/speech`，
但它同样生成歌曲，而非普通语音朗读。`/v1/models`提供模型信息。

```bash
curl --fail-with-body http://localhost:8087/v1/audio/music -H 'Content-Type: application/json' --data '{"model":"yue2","lyrics":"[Verse]\nMorning light across the floor","style":"English acoustic pop, warm singing","duration":30,"steps":8,"response_format":"opus"}' --output song.opus
```

原生`/synth`返回任务ID。轮询`/job?id=JOB_ID`直至`done`，再从
`/job?id=JOB_ID&result=1`获取包含音频、重放JSON和潜在表示的multipart结果。
参见[API指南](docs/API.md)、[本地API文档](http://localhost:8087/docs)及
[OpenAPI模式](http://localhost:8087/openapi.json)，本地文档可离线使用。

通过Streamable HTTP将MCP客户端连接到`http://localhost:8087/mcp`。
工具为`skill`、`generate_song`、`get_song`、`cancel_song`。智能体先阅读技能说明，
编写或整理完整歌曲，再生成并获取有效期一小时的HTTP下载链接。
工具不允许修改高级运行设置。详情见[MCP指南](docs/MCP.md)。

## 默认值与存储

默认使用**8步**、随机种子、**24,576令牌上下文**和2个声音变体。
音乐／语音兼容接口及MCP每次调用返回1首。时长是上限，歌曲可能提前结束。
正常启动会在各阶段之间释放模型权重。目前仅支持CUDA GPU发行配置。

所有生成接口共用1个串行工作线程，最多接收8个任务（包含活动任务）。
队列满时返回HTTP 429及`Retry-After`，请等待后重试。
`/health`、`/status`、`/system/queue`提供运行状态。
设置`YUE2_API_KEY`可保护`/v1`和`/mcp`；工作室与原生接口保持本地访问策略。
默认命令仅绑定localhost。

模型位于主机。`yue2-output`卷可在更换容器后保留已完成的结果。
原生结果默认保留24小时，智能体链接保留1小时。
浏览器IndexedDB曲库独立存储，请下载重要歌曲；模型目录不是浏览器曲库的备份。
参见[队列与结果存储](docs/QUEUE.md)。

## 文档与开发

[文档目录](docs/README.zh.md) · [Docker](docs/DOCKER.md) ·
[音频格式](docs/AUDIO.md) · [开发](docs/DEVELOPMENT.md) ·
[构建依赖](docs/BUILDING.md) · [基准测试](docs/BENCHMARKS.md)。
详细技术参考目前为英文；网站会明确提示尚无所选语言的译文。

有源码、Docker、Python和Task时，依次使用`task models`、`task build`、`task start`。
`task validate`检查工具、UI及原生CPU代码；`task test1`执行固定GPU基线。
`task pages`启动网站预览，`task pages-stop`停止预览。
基准分别记录冷启动、预热生成与显存，ASR仅作为不完美的趋势指标，不代表演唱质量结论。

## 隐私、来源与许可

生成在本机执行。下载会访问镜像仓库和模型托管站点，UI不依赖CDN。
请仅处理有权使用的歌词和录音，并负责任地分享结果。外部产品集成为独立范围。

[MAP](https://huggingface.co/m-a-p/YuE2-3B)提供模型，
[yue2.cpp](https://github.com/ServeurpersoCom/yue2.cpp)提供原生引擎。
Hangry Labs维护UI、API、打包和验证。项目代码采用[MIT许可](LICENSE)，
模型另受非商业使用条款约束。请阅读[模型来源](docs/MODELS.md)和
[第三方声明](THIRD_PARTY_NOTICES.md)。
联系：[contact@hangrylabs.app](mailto:contact@hangrylabs.app)。

<a id="version-history"></a>
<details markdown="1">
<summary><strong>版本历史</strong></summary>

### v0.1.0-snapshot

开发版包含本地工作室、原生／OpenAI兼容API、MCP、多语言界面、外部模型和已验证CUDA依赖。
尚未发布应用的稳定版本。

</details>
