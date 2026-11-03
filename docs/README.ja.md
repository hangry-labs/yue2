---
layout: default
title: ドキュメント
lang: ja
permalink: /docs/ja/
---
# ドキュメント

[English](README.md) · [Norsk bokmål](README.nb.md) · [Polski](README.pl.md) · **日本語** · [简体中文](README.zh.md) · [Español](README.es.md)

[クイックスタート](../README.ja.md#quick-start)から始めてください。
初回に2つのモデルを取得すれば、1行のDockerコマンドでCUDAコンテナーを起動できます。

## 歌詞から曲を作る

`http://localhost:8087`でスタジオを開きます。「歌詞」に歌う言葉を、
「曲のスタイル」にジャンル、楽器、言語、声質を入力します。
`[Verse]`や`[Chorus]`で構成を示せます。「新しい曲」は毎回作曲し、ABC譜面や
音声コードの再生成は指定した旋律や演奏を再利用します。表示言語を変えても歌詞は翻訳しません。

既定は8ステップ、音響2バリエーションです。1〜3個を選べます。
指定時間は上限です。残したい曲はダウンロードしてください。
ブラウザーのライブラリとサーバーの結果ボリュームは別管理です。

## APIとMCP

`POST /v1/audio/music`または`/v1/audio/speech`は完成した1つのファイルを返します。
`POST /synth`はジョブを作り、`/job?id=JOB_ID`で状態を確認します。
ローカルの`/docs`と`/openapi.json`に契約を記載しています。
MCPは`/mcp`のStreamable HTTPです。先に`skill`を読み、`generate_song`で生成、
`get_song`で確認、`cancel_song`で中止します。完了リンクは1時間有効です。

## 詳細ガイド

以下の技術資料は英語です。サイトは言語の選択を保持し、未翻訳のページには案内を表示します。

| ガイド | 内容 |
| --- | --- |
| [Docker](DOCKER.md) | 起動、GPU、マウント、ネットワーク |
| [モデル](MODELS.md) | 取得、チェックサム、追加モデル |
| [音声形式](AUDIO.md) | 入力、可逆／非可逆出力 |
| [API](API.md) | OpenAI互換、ジョブ、認証 |
| [MCP](MCP.md) | ツール、スキル、制限、リンク |
| [キューと保存](QUEUE.md) | 容量、キャンセル、HTTP 429、永続化 |
| [アダプター](ADAPTERS.md) | ローカルLoRAファイルと強度 |
| [エンジン](ARCHITECTURE.md) | ABC、リクエスト項目、ネイティブツール |
| [開発](DEVELOPMENT.md) | Task、構成、ローカルデータ |
| [ビルド](BUILDING.md) | 検証済みCUDA依存関係とロールバック |
| [ベンチマーク](BENCHMARKS.md) | 時間、VRAM、ASR評価の限界 |
| [ウェブサイト](WEBSITE.md) | プレビューと公開 |
| [リリース](RELEASING.md) | バージョン、レジストリ、検証 |

モデルの条件とアプリのライセンスは別です。[MIT](../LICENSE)と
[第三者ライセンス](../THIRD_PARTY_NOTICES.md)を参照してください。
