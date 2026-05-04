# CLI

[Back to README](../README.md)

## Entry Point

Use `cli.bat` from the repository root:

```powershell
cd C:\apps\TimelineForChatGPT
.\cli.bat <command>
```

`cli.bat` starts the PowerShell wrapper and runs the worker through Docker Compose.

## Settings Commands

```powershell
.\cli.bat settings init
.\cli.bat settings status
.\cli.bat settings output show
.\cli.bat settings output set C:\TimelineData\chatgpt
```

## Item Commands

```powershell
.\cli.bat items refresh --file C:\path\chatgpt-export.zip --json
.\cli.bat items refresh --file C:\path\chatgpt-export.zip --download-to C:\path\handoff --json
.\cli.bat items list --json
.\cli.bat items list --page 1 --page-size 100 --json
.\cli.bat items download --to C:\path\handoff
```

## List Behavior

`items list` returns every item by default. Use `--page` or `--page-size` only when one page is needed.

Items are sorted latest-first by:

- `updated_at`
- `ended_at_utc`
- `created_at`
- `started_at_utc`
- `conversation_id`

## Download Behavior

`items download --to` builds a ZIP from the current output root. Existing ZIP files are not overwritten unless `--overwrite` is passed.
