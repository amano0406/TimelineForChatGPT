# TimelineForChatGPT

`TimelineForChatGPT` converts a ChatGPT export ZIP into per-conversation output artifacts and a small ZIP package for handoff to another tool or LLM.

This product is CLI-only. There is no Web UI. Normal operation is Windows PowerShell first and Docker-only behind it.

## What It Does

- Reads one ChatGPT export ZIP specified at refresh time.
- Treats that ZIP as the source of truth for the current output.
- Rebuilds the current output from scratch on `items refresh --file`.
- Preserves conversation order, message order, final exported title, and attachment references.
- Writes per-conversation `timeline.json` focused on `user` / `assistant` / `system` messages.
- Writes per-conversation `convert_info.json` with conversion metadata.
- Produces a timestamped `TimelineForChatGPT-export-<run-id>.zip`.
- Leaves date filtering and global timeline rendering to downstream Timeline products.

## What It Does Not Do

- It does not provide a Web UI.
- It does not scan configured input directories as the normal workflow.
- It does not delete, move, rename, or overwrite the source export ZIP.
- It does not export binary attachment files into the handoff ZIP.
- It does not reconstruct title rename history. Current ChatGPT exports expose the final title only.
- It does not apply date or month range limits.

## Settings

Normal Docker Compose operation uses the repo-root local settings file:

```text
C:\apps\TimelineForChatGPT\settings.json
```

The repo keeps a Git-managed template:

```text
C:\apps\TimelineForChatGPT\settings.example.json
```

`settings.json` is intentionally not committed. It is created from `settings.example.json` when missing.

The settings file contains one user-controlled path:

```json
{
  "outputRoot": "C:\\TimelineData\\chatgpt"
}
```

- `outputRoot`: current rebuilt per-conversation artifacts and manifest

Run history, locks, and cache are product-managed Docker runtime data. They are not settings.

The settings file does not contain input directories. The input ZIP is passed explicitly:

```powershell
.\cli.bat items refresh --file C:\path\chatgpt-export.zip --json
```

## Output Layout

Each refresh uses a Docker-managed run directory under the internal `app-data` volume and replaces the current output under `outputRoot`.

```text
<outputRoot>/
  manifest.json
  <conversation-id>/
    convert_info.json
    timeline.json

<internal app-data volume>/
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

`outputRoot` is bind-mounted to `C:\TimelineData\chatgpt` by Docker Compose. Run/state history lives in the Docker named volume `app-data`. Cache files live in `cache-data`. Upload staging and handoff staging are copied through `cache-data` and removed after the CLI command completes. Use `--download-to` or `items download --to` when a ZIP handoff should be copied to the host.

The download ZIP contains only the handoff files:

- `README.md`
- `items/<conversation-id>/convert_info.json`
- `items/<conversation-id>/timeline.json`

`timeline.json` intentionally contains a simple `title` field. It does not contain `title_source` or `title_history_available`.

## CLI Usage

Run commands from the repository root:

```powershell
cd C:\apps\TimelineForChatGPT
```

Use `cli.bat` as the public Windows entrypoint. It invokes PowerShell and runs the worker through Docker Compose:

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

Notes:

- `items refresh --file` clears and rebuilds the output from the specified ZIP.
- `--file` may point outside this repository when using `cli.bat`; the wrapper copies the file into a temporary Docker path and leaves the original untouched.
- `items list` sorts conversations latest-first by `updated_at`, then `ended_at_utc`, `created_at`, `started_at_utc`, and `conversation_id`. The default is all items. Use `--page` or `--page-size` when one page is needed; paging defaults to `--page 1 --page-size 100`. There is no `--all` option because all items are already the default. It reads the current `manifest.json` directly and does not use a separate list cache.
- `items download --to` builds a ZIP from the current output and does not overwrite an existing file unless `--overwrite` is passed.
- `--download-to` on `items refresh` refreshes and copies the ZIP in one command.
- `runs` commands are diagnostic-only because run directories are Docker-managed runtime files.
- Date range options are intentionally absent. Filtering belongs to downstream Timeline products.

## Docker Compose

In normal Windows operation, use `.\cli.bat` rather than typing Docker commands directly.

The Compose project name is:

```text
timeline-for-chatgpt
```

The worker service runs the Python CLI. It exposes no browser port.

WSL or direct Docker usage remains a development back door:

```bash
cd /mnt/c/apps/TimelineForChatGPT
docker compose up -d worker
docker compose exec -T worker python -m timeline_for_chatgpt_worker settings status --json
```

For host file handoff, prefer `.\cli.bat`. The wrapper copies input/output files through `docker cp` under the Docker `cache-data` volume and reuses the Compose-managed `worker-1` container instead of creating one-off `worker-run-*` containers. Long host filenames are shortened for the container-side temporary filename.

The PowerShell wrapper reads `settings.json` and passes `outputRoot` to Docker Compose as the host bind mount. With the default settings, that mount is `C:\TimelineData\chatgpt`. Runtime state and cache are Docker named volumes: `app-data` and `cache-data`. It does not bind-mount `runs`, `uploads`, `state`, or cache directories to the host.

Host Python CLI execution is intentionally blocked:

```bash
PYTHONPATH=worker/src python3 -m timeline_for_chatgpt_worker items list
```

Set `TIMELINE_FOR_CHATGPT_ALLOW_HOST_CLI=1` only for unit tests or intentional local development harnesses.

## Validation

Docker test entrypoint:

```powershell
.\scripts\test.ps1
```

Local `cli.ps1` refresh and download smoke test:

```powershell
python tests/smoke/run_cli_ps1_download.py
```

This smoke test does not rewrite the normal `settings.json`. It creates a temporary settings file, a dedicated Docker Compose project, and temporary app-data/cache/output directories under `C:\TimelineData\tfcg-cli-ps1-smoke-*`, then removes them unless `--preserve-output` is passed.

Include that smoke test after the Docker unit tests:

```powershell
.\scripts\test.ps1 -IncludeLocalCliDownload
```

Host Python tests are development-only and require the explicit override:

```bash
TIMELINE_FOR_CHATGPT_ALLOW_HOST_CLI=1 PYTHONPATH=/mnt/c/apps/TimelineForChatGPT/worker/src python3 -m unittest discover -s /mnt/c/apps/TimelineForChatGPT/worker/tests -v
```

## Current Boundary

Included:

- ChatGPT export ZIP parsing
- conversation graph current-branch normalization
- per-conversation `timeline.json`
- per-conversation `convert_info.json`
- small ZIP handoff package
- current run pointer and refresh history
- corrupted ZIP rejection through the parser/ZIP reader

Not included:

- Web UI
- date/month filtering
- binary attachment transcription/OCR
- title rename history recovery
- automatic multi-input directory scanning as the normal path

## Repo Layout

```text
docker/
docs/
scripts/
worker/
cli.ps1
cli.bat
settings.example.json
```
