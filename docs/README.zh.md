---
layout: default
title: 文档
lang: zh
permalink: /docs/zh/
---
# 文档

[English](README.md) · [Norsk bokmål](README.nb.md) · [Polski](README.pl.md) · [日本語](README.ja.md) · **简体中文** · [Español](README.es.md)

请先阅读[快速开始](../README.zh.md#quick-start)：首次下载两个模型后，
即可通过一条Docker命令启动CUDA容器。

## 从歌词到歌曲

打开`http://localhost:8087`。在“歌词”中填写要演唱的文字，在“音乐风格描述”中
填写曲风、乐器、语言及声线。`[Verse]`、`[Chorus]`等标签用于描述结构。
“新建歌曲”每次重新作曲；ABC乐谱与音频编码重放用于明确复用旋律或演出。
界面语言不会翻译歌词。

默认8步与2个声音变体，可选择1至3个。时长为上限，模型可能提前结束。
请下载需要保留的歌曲。浏览器曲库与服务器输出卷是独立存储。

## API与MCP

`POST /v1/audio/music`或`/v1/audio/speech`返回一个完整音频文件。
`POST /synth`创建任务，通过`/job?id=JOB_ID`查询。
本地`/docs`与`/openapi.json`描述接口契约。
MCP位于`/mcp`，采用Streamable HTTP。先读取`skill`，使用`generate_song`生成，
用`get_song`查询、`cancel_song`取消。完成后的链接有效期为一小时。

## 详细指南

以下技术参考目前为英文。网站会保留语言偏好，并在文档尚未翻译时显示明确提示。

| 指南 | 内容 |
| --- | --- |
| [Docker](DOCKER.md) | 启动、GPU、挂载与网络 |
| [模型](MODELS.md) | 下载、校验值与可选模型 |
| [音频格式](AUDIO.md) | 导入、有损与无损导出 |
| [API](API.md) | OpenAI兼容性、任务与认证 |
| [MCP](MCP.md) | 工具、技能、智能体限制与链接 |
| [队列与存储](QUEUE.md) | 容量、取消、HTTP 429与持久化 |
| [适配器](ADAPTERS.md) | 本地LoRA文件与强度 |
| [引擎参考](ARCHITECTURE.md) | ABC、请求字段与原生工具 |
| [开发](DEVELOPMENT.md) | Task、仓库结构与本地数据 |
| [构建](BUILDING.md) | 已验证的CUDA依赖与回退 |
| [基准测试](BENCHMARKS.md) | 时间、显存与ASR评估的局限 |
| [网站](WEBSITE.md) | 本地预览与发布 |
| [版本发布](RELEASING.md) | 版本、仓库与验证 |

模型条款与应用许可分别适用。请参阅[MIT许可](../LICENSE)与
[第三方声明](../THIRD_PARTY_NOTICES.md)。
