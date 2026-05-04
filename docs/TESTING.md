# Testing

[Back to README](../README.md)

## Docker Unit Tests

```powershell
cd C:\apps\TimelineForChatGPT
.\scripts\test.ps1
```

## Local CLI Smoke Test

```powershell
cd C:\apps\TimelineForChatGPT
python tests/smoke/run_cli_ps1_download.py
```

This smoke test uses a temporary settings file, temporary output root, and dedicated Docker Compose project. It does not rewrite the normal `settings.json`.

## Combined Test

```powershell
.\scripts\test.ps1 -IncludeLocalCliDownload
```

## Host Python Tests

Host Python CLI execution is blocked for normal operation. Unit tests may use:

```bash
TIMELINE_FOR_CHATGPT_ALLOW_HOST_CLI=1 PYTHONPATH=/mnt/c/apps/TimelineForChatGPT/worker/src python3 -m unittest discover -s /mnt/c/apps/TimelineForChatGPT/worker/tests -v
```
