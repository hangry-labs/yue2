<p align="center"><img src="web/src/assets/yue2_logo_horizontal.webp" alt="Hangry Labs YuE2" width="900"></p>

<p align="center"><a href="README.md">English</a> · <a href="README.nb.md">Norsk bokmål</a> · <a href="README.pl.md">Polski</a> · <strong>日本語</strong> · <a href="README.zh.md">简体中文</a> · <a href="README.es.md">Español</a></p>

<p align="center"><a href="https://hangry-labs.github.io/yue2/examples/?lang=ja"><strong>🎧 生成した曲を聴く</strong></a></p>

# Hangry Labs YuE2

バージョン **v1.0.0**。[バージョン履歴](#version-history)もご覧ください。

歌詞と曲のスタイルから、自分のGPUで楽曲を生成します。1つのDockerコンテナーに
ブラウザースタジオ、HTTP API、MCP、48 kHzステレオ出力をまとめています。
[yue2.cpp](https://github.com/ServeurpersoCom/yue2.cpp)、C++20、GGMLを使用しています。

<a id="quick-start"></a>

## クイックスタート

NVIDIA GPUに対応したDockerと、CUDA 12.9.1互換ドライバーが必要です。
検証済み環境は**RTX 5070 Ti、VRAM 16 GB**です。他のGPU構成は未検証です。
最初に[2つのモデル](#model-downloads)を`data/models/`へ保存してください。
`data/`を含むディレクトリーから、次のどちらか1行を実行します。

**Bash：**

```bash
docker run -d --name yue2 --restart unless-stopped --gpus all -p 127.0.0.1:8087:8087 --mount "type=bind,source=$(pwd)/data/models,target=/models,readonly" --mount type=volume,source=yue2-output,target=/output hangrylabs/yue2:v1.0.0@sha256:446bd69099513f8b1d762656d455826872b7221ab232aa05e907f3ada90c9b34
```

**PowerShell：**

```powershell
docker run -d --name yue2 --restart unless-stopped --gpus all -p 127.0.0.1:8087:8087 --mount "type=bind,source=$($PWD.Path)\data\models,target=/models,readonly" --mount type=volume,source=yue2-output,target=/output hangrylabs/yue2:v1.0.0@sha256:446bd69099513f8b1d762656d455826872b7221ab232aa05e907f3ada90c9b34
```

**[http://localhost:8087](http://localhost:8087)**を開き、歌詞とスタイルを入力して
「曲を生成」を選びます。ホスト側にPythonやコンパイラーは不要です。
上のコマンドは安定版 `v1.0.0` を固定します。`latest` は開発版を追跡します。
同じ安定版は `ghcr.io/hangry-labs/yue2:v1.0.0@sha256:446bd69099513f8b1d762656d455826872b7221ab232aa05e907f3ada90c9b34` からも取得できます。

<details markdown="1">
<summary><strong>初回の準備：モデルのダウンロード</strong></summary>

<a id="model-downloads"></a>

`data/models/`を作り、元のファイル名のまま保存します。合計約4.34 GBです。

| モデル | 用途 | サイズ |
| --- | --- | --- |
| [YuE2-3B-Q8_0.gguf](https://huggingface.co/Serveurperso/YuE2-GGUF/resolve/e630f2b8f6aedf8254c3186438633c1b5eeaf80a/YuE2-3B-Q8_0.gguf) | 楽曲生成 | 3.81 GB |
| [YuE2-Vae-F32.gguf](https://huggingface.co/Serveurperso/YuE2-GGUF/resolve/e630f2b8f6aedf8254c3186438633c1b5eeaf80a/YuE2-Vae-F32.gguf) | 音声エンコード／デコード | 530 MB |

[モデル一覧](docker/models.json)にSHA-256を記載しています。ソースを取得している場合は
`task models`でダウンロードと検証ができます。重みはイメージに含めず、サーバーも
自動取得しません。イメージとモデルの準備後はオフラインで生成できます。
モデルの利用条件はアプリのライセンスとは別です。

</details>

## 主な機能

- スタイルと歌詞からの生成。コード付き譜面、メロディーのみ、譜面なしのモード。
- 48 kHzステレオのOpus、MP3、Ogg、FLAC、WAV、AAC/M4A出力。
- 検索、お気に入り、再生、入力の再利用ができるブラウザー内ライブラリ。
- ABC譜面の編集、意味コードからの再生成、元音声からの続きの生成。
- 同じ作曲に対して1〜3個の音響バリエーション。既定は2個。
- ローカルLoRAアダプターと、音声・潜在表現のVAE変換。
- 非同期ジョブ、キャンセル、キュー上限、永続ボリュームへの結果保存。
- システム画面のモデル状態、キュー、保存容量、NVIDIA GPUグラフ。
- ネイティブHTTP API、OpenAI互換クライアント、エージェント向けMCP。

譜面への変換と音声のトークン化には、追加モデルとサーバー引数が必要です。
標準のダウンロードには含みません。[モデルの説明](docs/MODELS.md)をご覧ください。

## ブラウザースタジオ

<p align="center"><a href="assets/screenshots/create-ui.webp"><img src="assets/screenshots/create-ui.webp" alt="YuE2の楽曲作成画面" width="1200"></a></p>

ヘッダーで英語、ノルウェー語ブークモール、ポーランド語、日本語、簡体字中国語、
スペイン語を選べます。ブラウザーが選択を記憶します。直接アクセスするパスは
`/en`、`/nb`、`/pl`、`/ja`、`/zh`、`/es`です。切り替えても歌詞、設定、処理中の
ジョブは保持します。表示言語は歌唱言語を指定せず、歌詞も翻訳しません。

「新しい曲」は現在の歌詞とスタイルから毎回作曲します。「ABC譜面を使う」は
指定の旋律を保持します。音声コードからの再生成は既存の演奏を使うため、歌詞を
編集しても保存済みの歌唱は書き換わりません。ジャンル、楽器、雰囲気、声質は
スタイル欄へ、`[Verse]`や`[Chorus]`などの構成は歌詞欄へ入力します。
これらはモデルへのヒントで、厳密な制御を保証するものではありません。

## APIとエージェント

`/v1/audio/music`は完成した音声ファイルを返します。OpenAIクライアントには
`/v1/audio/speech`を使えますが、通常の読み上げではなく音楽を生成します。
`/v1/models`でモデル情報を確認できます。

```bash
curl --fail-with-body http://localhost:8087/v1/audio/music -H 'Content-Type: application/json' --data '{"model":"yue2","lyrics":"[Verse]\nMorning light across the floor","style":"English acoustic pop, warm singing","duration":30,"steps":8,"response_format":"opus"}' --output song.opus
```

ネイティブ`/synth`はジョブIDを返します。`/job?id=JOB_ID`が`done`になるまで確認し、
`/job?id=JOB_ID&result=1`から音声、再生成用JSON、潜在表現をmultipartで取得します。
[APIガイド](docs/API.md)、[ローカルの説明](http://localhost:8087/docs)、
[OpenAPIスキーマ](http://localhost:8087/openapi.json)も利用できます。

MCPクライアントはStreamable HTTPで`http://localhost:8087/mcp`へ接続します。
ツールは`skill`、`generate_song`、`get_song`、`cancel_song`です。先にスキルを読み、
曲全体の歌詞とスタイルを準備して生成すると、1時間有効なHTTPリンクを受け取れます。
エージェントは高度な実行環境設定を変更できません。[MCPガイド](docs/MCP.md)を参照してください。

## 既定値と保存

既定は**8ステップ**、ランダムシード、**24,576トークン**のコンテキスト、音響2種です。
互換音声APIとMCPは1回の呼び出しで1曲を返します。指定時間は上限であり、早く終わる
場合があります。通常の起動では段階間で重みを解放します。対応するGPU配布はCUDAのみです。

全生成経路で1つの直列ワーカーと、実行中を含め8件のキューを共有します。
満杯時はHTTP 429と`Retry-After`を返すため、待ってから再試行してください。
`/health`、`/status`、`/system/queue`が稼働状況を返します。`YUE2_API_KEY`は`/v1`と
`/mcp`を保護します。スタジオとネイティブAPIは従来のローカルアクセス方針で、
既定コマンドはlocalhostだけに公開します。

モデルはホスト側に保存します。`yue2-output`ボリュームの完了結果はコンテナーを
交換しても残ります。通常の結果は既定24時間、エージェントリンクは1時間です。
ブラウザーのIndexedDBライブラリは別管理なので、大切な曲はダウンロードしてください。
モデルフォルダーはライブラリのバックアップにはなりません。[保存とキュー](docs/QUEUE.md)も参照してください。

## ドキュメントと開発

[ドキュメント一覧](docs/README.ja.md) · [Docker](docs/DOCKER.md) ·
[音声形式](docs/AUDIO.md) · [開発](docs/DEVELOPMENT.md) ·
[ビルド依存関係](docs/BUILDING.md) · [ベンチマーク](docs/BENCHMARKS.md)。
詳細な技術資料は英語です。サイトでは未翻訳のページに案内を表示します。

ソース、Docker、Python、Taskを用意すると`task models`、`task build`、`task start`を
使えます。`task validate`はツール、UI、ネイティブCPUコードを検証し、`task test1`は
固定GPUテストを実行します。サイトのプレビューは`task pages`、停止は`task pages-stop`です。
ベンチマークはコールド起動、ウォーム生成、VRAMを分けます。ASRは不完全な傾向指標です。

## プライバシー、出典、ライセンス

生成は自分のマシン内で行います。取得時はレジストリとモデル配布元へ接続しますが、
UIにCDNは不要です。扱う権利のある素材を使い、結果を責任を持って共有してください。
外部製品との統合は別の範囲です。

モデルは[MAP](https://huggingface.co/m-a-p/YuE2-3B)、ネイティブエンジンは
[yue2.cpp](https://github.com/ServeurpersoCom/yue2.cpp)が提供します。
Hangry LabsはUI、API、パッケージ化、検証を担当します。プロジェクトのコードは
[MIT](LICENSE)、モデルは別途非商用条件の対象です。
[モデルの出典](docs/MODELS.md)と[第三者ライセンス](THIRD_PARTY_NOTICES.md)をご確認ください。
連絡先：[contact@hangrylabs.app](mailto:contact@hangrylabs.app)。

<a id="version-history"></a>
<details markdown="1">
<summary><strong>バージョン履歴</strong></summary>

### v1.0.0

ローカルスタジオ、ネイティブ／OpenAI互換API、MCP、多言語UI、外部モデル、
検証済みCUDA依存ライブラリを含む初の安定版です。
2026年11月3日公開。[リリースノート](https://github.com/hangry-labs/yue2/releases/tag/v1.0.0)をご覧ください。
クイックスタートは安定版タグと検証済みOCIダイジェストを固定します。

</details>
