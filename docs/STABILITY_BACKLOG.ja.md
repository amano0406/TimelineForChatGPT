# Stability Backlog

`TimelineForChatGPT` の安定性を上げるための作業整理です。
通常の `settings.json` や本番 `outputRoot` をテストに巻き込まないことを最優先にします。

## 現状

- Docker unit test は `scripts/test.ps1` で実行できる。
- `cli.ps1` 経由の refresh / download smoke test がある。
- smoke test は一時 settings path、専用 Docker Compose project、一時 app-data/cache/output を使う。
- smoke test は通常の `settings.json` が変化していないことを検証する。
- テスト用の一時 Docker project / volume / output directory は通常削除される。

## 優先度高

1. `items refresh --file ... --download-to ...` の smoke test を追加する。
   現在の smoke は refresh と download を分けて確認しているため、実運用で使う一括導線も確認する。

2. `items list` の smoke test を refresh 後に追加する。
   最新順、全件既定、pagination 指定時の件数、fixture conversation の存在を Docker wrapper 経由で確認する。

3. 入力 ZIP の異常系 fixture を増やす。
   corrupted ZIP、`conversations.json` 欠落、空 conversation、壊れた `mapping`、複数 conversation、`conversations-*.json` を分けて確認する。

4. Windows path / long filename の smoke test を追加する。
   長い ZIP ファイル名、空白を含む path、短縮後の container temp filename、download 先の既存 ZIP without `--overwrite` を確認する。

5. smoke cleanup の検証を明示化する。
   smoke 完了後に `tfcg-cli-ps1-smoke-*` の directory、Compose project、volume、temporary image が残らないことを検証する。

## 優先度中

1. 実 export を使う任意のローカル専用 smoke test を追加する。
   CI には載せず、`--export C:\path\chatgpt-export.zip --preserve-output` のような明示指定に限定する。

2. large export 向けの性能・容量ログを出す。
   conversation count、message count、attachment reference count、input ZIP size、output ZIP size、processing duration を smoke summary に含める。

3. attachment reference の fixture を増やす。
   画像、PDF、音声、存在しない添付参照、同名ファイル、深い相対 path を確認する。

4. `manifest.json` / `timeline.json` / `convert_info.json` の schema 互換チェックを追加する。
   破壊的なフィールド削除や `thread.json` 復活をテストで検出する。

5. `logs/worker.log` と `result.json` の失敗時 contract を固める。
   conversation-level failure と run-level failure を分け、診断に必要な情報が残ることを確認する。

## 優先度低

1. GitHub Actions で Docker unit test だけを実行する。
   Windows + Docker Compose の実運用 smoke はローカル優先にする。

2. Timeline family 共通の smoke runner を作る。
   ただし `testMode` は settings に入れず、各 product の一時 settings path と一時 output root を使う。

3. 大規模 export の regression corpus を作る。
   個人データを含まない synthetic export を生成し、CI に載せられる範囲だけを管理する。

## やらない

- `settings.json` に `testMode` を追加しない。
- 本番 `outputRoot` を smoke test の出力先にしない。
- 実ユーザーデータや実 export ZIP を Git 管理しない。
- テストのために通常 worker container や通常 named volume を破壊しない。
