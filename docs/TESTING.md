# Testing

[Back to README](../README.md)

## Docker Unit Tests

```powershell
cd C:\apps\TimelineForChatGPT
.\scripts\test.ps1
```

## Combined Test

```powershell
.\scripts\test.ps1 -IncludeLocalApiSmoke
```

## Host Python Tests

Host Python CLI execution is blocked for normal operation. Unit tests may use:

PowerShell:

```powershell
cd C:\apps\TimelineForChatGPT
$env:TIMELINE_FOR_CHATGPT_ALLOW_HOST_CLI = "1"
$env:PYTHONPATH = "C:\apps\TimelineForChatGPT\worker\src"
python -m unittest discover -s worker\tests -v
```

Bash / WSL:

```bash
TIMELINE_FOR_CHATGPT_ALLOW_HOST_CLI=1 PYTHONPATH=/mnt/c/apps/TimelineForChatGPT/worker/src python3 -m unittest discover -s /mnt/c/apps/TimelineForChatGPT/worker/tests -v
```
