# TimelineForChatGPT worker

Python worker that polls pending jobs, parses ChatGPT export ZIP files, and writes timeline-oriented outputs.

## Docker CLI

From the repo root, prefer the Windows PowerShell entrypoints:

```powershell
.\scripts\config-check.ps1
.\scripts\refresh.ps1
.\scripts\test.ps1
```

For WSL and non-Windows shells, use Docker Compose directly as the backdoor path.

Refresh configured input directories:

```bash
docker compose run --rm worker refresh
```

The latest human-readable refresh summary is written as `refresh-latest.md` in the configured output root.
The stable known-input catalog is written as `index.md` and `index.json` in the same output root.

Validate the config without processing:

```bash
docker compose run --rm worker config-check
```

Process one file directly:

```bash
docker compose run --rm worker process /workspace/data/inputs/chatgpt-export.zip --output-root /workspace/data/outputs
```

The command creates one run directory, processes the export, and prints the run directory path.

Host Python CLI execution is intentionally blocked for normal operation. Set `TIMELINE_FOR_CHATGPT_ALLOW_HOST_CLI=1` only for tests.
