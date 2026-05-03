# TimelineForChatGPT

`TimelineForChatGPT` は、ChatGPT の export ZIP を読み取り、会話ごとの成果物と、他ツールや LLM に渡しやすい小さな ZIP を生成するローカル CLI ツールです。

この製品に Web UI はありません。通常利用は Windows PowerShell を入口にし、実処理は Docker Compose 管理の worker コンテナ内で行います。

## できること

- 指定された ChatGPT export ZIP を 1 つ読む
- その ZIP を現在の出力の正本として扱う
- `items refresh --file` 実行時に現在の出力を作り直す
- conversation の順序、message の順序、最終 export タイトル、添付参照を維持する
- conversation ごとに `timeline.json` を出力する
- conversation ごとに `convert_info.json` を出力する
- `TimelineForChatGPT-export-<run-id>.zip` を生成する
- 日付範囲の抽出や全体 timeline 化は後段の Timeline 製品に任せる

## やらないこと

- Web UI は提供しない
- 通常フローでは入力ディレクトリをスキャンしない
- 元の export ZIP を削除、移動、改名、上書きしない
- 添付ファイル本体を handoff ZIP に含めない
- タイトル変更履歴は復元しない
- 日付や月単位の絞り込みは行わない

## 設定

通常の Docker Compose 実行では、repo 直下のローカル設定を使います。

```text
C:\apps\TimelineForChatGPT\settings.json
```

Git 管理されるテンプレートは次です。

```text
C:\apps\TimelineForChatGPT\settings.example.json
```

`settings.json` は Git 管理しません。存在しない場合は `settings.example.json` から作成されます。

設定できるユーザー向け項目は `outputRoot` だけです。

```json
{
  "outputRoot": "C:\\TimelineData\\chatgpt"
}
```

- `outputRoot`: 現在の conversation 別成果物と `manifest.json` の出力先

run 履歴、lock、cache は Docker 内の製品管理データです。ユーザー設定ではありません。

入力ディレクトリは設定しません。入力 ZIP はコマンドで明示します。

```powershell
.\cli.bat items refresh --file C:\path\chatgpt-export.zip --json
```

## 出力構成

各 refresh は Docker 内の `app-data` volume に run データを作り、`outputRoot` の現在出力を置き換えます。

```text
<outputRoot>/
  manifest.json
  <conversation-id>/
    convert_info.json
    timeline.json

<Docker internal app-data volume>/
  <run-id>/
    request.json
    status.json
    result.json
    manifest.json
    export_summary.json
    conversation_index.jsonl
    conversations/
    llm/
    export/TimelineForChatGPT-export-<run-id>.zip
  current.json
  refresh-history.jsonl
```

既定では `outputRoot` は `C:\TimelineData\chatgpt` です。Docker Compose ではこのパスを `/workspace/output` に bind mount します。run や cache は Docker named volume の `app-data` と `cache-data` に保存されます。

handoff 用 ZIP に含まれるのは次だけです。

- `README.md`
- `items/<conversation-id>/convert_info.json`
- `items/<conversation-id>/timeline.json`

`timeline.json` は単純な `title` フィールドだけを持ちます。`title_source` や `title_history_available` は持ちません。

## CLI

repo 直下で実行します。

```powershell
cd C:\apps\TimelineForChatGPT
```

Windows では `cli.bat` を公開入口にします。PowerShell wrapper 経由で Docker Compose 管理の worker を実行します。

```powershell
.\cli.bat settings init
.\cli.bat settings status
.\cli.bat settings output show
.\cli.bat settings output set C:\TimelineData\chatgpt

.\cli.bat items refresh --file C:\path\chatgpt-export.zip --json
.\cli.bat items refresh --file C:\path\chatgpt-export.zip --download-to C:\path\handoff --json
.\cli.bat items list --json
.\cli.bat items list --page 1 --page-size 100 --json
.\cli.bat items download --to C:\path\handoff
```

補足:

- `items refresh --file` は、指定 ZIP から現在の出力を作り直します。
- `--file` は repo 外の ZIP を指定できます。`cli.bat` が Docker 内の一時領域へコピーし、元ファイルは変更しません。
- `items list` は `updated_at`, `ended_at_utc`, `created_at`, `started_at_utc`, `conversation_id` の優先順で新しいもの順に返します。
- `items list` の既定は全件取得です。
- 1ページだけ必要な場合は `--page` または `--page-size` を指定します。ページング時の既定は `--page 1 --page-size 100` です。
- 全件取得は既定動作なので、`--all` オプションはありません。
- `items list` は現在の `manifest.json` を直接読みます。別の一覧 cache は使いません。
- `items download --to` は現在の出力から ZIP を作ります。既存ファイルは `--overwrite` なしでは上書きしません。
- `--download-to` は refresh と ZIP コピーをまとめて行います。
- `runs` 系コマンドは診断用です。run データは Docker 管理の内部データです。
- 日付範囲オプションはありません。絞り込みは後段の Timeline 製品で行います。

## Docker Compose

通常の Windows 運用では、Docker コマンドを直接打たずに `.\cli.bat` を使います。

Compose project name は次です。

```text
timeline-for-chatgpt
```

worker service は Python CLI を実行します。ブラウザ用ポートは公開しません。

WSL や Docker 直接実行は開発用の裏口として残します。

```bash
cd /mnt/c/apps/TimelineForChatGPT
docker compose up -d worker
docker compose exec -T worker python -m timeline_for_chatgpt_worker settings status --json
```

ホストファイルの受け渡しは `.\cli.bat` を優先します。wrapper は Docker の `cache-data` volume 経由で `docker cp` を使い、Compose 管理の `worker-1` を使い回します。長いホストファイル名は Docker 内の一時ファイル名として短縮されます。

PowerShell wrapper は `settings.json` を読み、`outputRoot` を Docker Compose の host bind mount として渡します。既定では `C:\TimelineData\chatgpt` です。runtime state と cache は Docker named volume の `app-data` と `cache-data` です。

ホスト Python での CLI 直接実行は通常ブロックされます。

```bash
PYTHONPATH=worker/src python3 -m timeline_for_chatgpt_worker items list
```

`TIMELINE_FOR_CHATGPT_ALLOW_HOST_CLI=1` は、単体テストや明示的な開発用 harness の場合だけ使います。

## 検証

Docker 内でテストします。

```powershell
.\scripts\test.ps1
```

ローカル `cli.ps1` refresh / download smoke test:

```powershell
python tests/smoke/run_cli_ps1_download.py
```

この smoke test は通常の `settings.json` を書き換えません。一時 settings file、専用 Docker Compose project、一時 app-data/cache/output directory を `C:\TimelineData\tfcg-cli-ps1-smoke-*` 配下に作成し、`--preserve-output` 指定時以外は削除します。

Docker unit tests の後にこの smoke test も含める場合:

```powershell
.\scripts\test.ps1 -IncludeLocalCliDownload
```

安定性向上の残作業は [docs/STABILITY_BACKLOG.ja.md](docs/STABILITY_BACKLOG.ja.md) に整理しています。

ホスト Python テストは開発用です。明示的な override が必要です。

```bash
TIMELINE_FOR_CHATGPT_ALLOW_HOST_CLI=1 PYTHONPATH=/mnt/c/apps/TimelineForChatGPT/worker/src python3 -m unittest discover -s /mnt/c/apps/TimelineForChatGPT/worker/tests -v
```

## 現在の境界

含むもの:

- ChatGPT export ZIP の parsing
- conversation graph の current branch 正規化
- conversation ごとの `timeline.json`
- conversation ごとの `convert_info.json`
- 小さな ZIP handoff package
- current run pointer と refresh history
- 壊れた ZIP の rejection

含まないもの:

- Web UI
- 日付や月単位の絞り込み
- 添付ファイル本体の transcription / OCR
- タイトル変更履歴の復元
- 通常フローとしての複数入力ディレクトリ自動スキャン

## Repo 構成

```text
docker/
docs/
scripts/
worker/
cli.ps1
cli.bat
settings.example.json
```
