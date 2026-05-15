# TimelineForChatGPT

## What This Product Does

TimelineForChatGPT converts one ChatGPT export ZIP into per-conversation timeline artifacts. It is a local Windows CLI product: `cli.bat` is the normal command entrypoint, and the conversion worker runs through Docker Compose.

The output is designed to be easy to inspect, package, and hand off to another Timeline product or an LLM workflow.

`start.ps1` also starts a small local health API. The health API is only for runtime readiness checks; product operations are still performed through the CLI.

## Runtime

```powershell
cd C:\apps\TimelineForChatGPT
.\start.ps1
```

`start.ps1` starts:

- `worker`: Python conversion worker.
- `api`: C# health service for `GET /health`.

Stop the services without deleting generated data:

```powershell
.\stop.ps1
```

## Settings

The local settings file is:

```text
C:\apps\TimelineForChatGPT\settings.json
```

Expected shape:

```json
{
  "schemaVersion": 1,
  "runtime": {
    "instanceName": "29b8a84688",
    "apiPort": 19300
  },
  "outputRoot": "C:\\TimelineData\\chatgpt"
}
```

- `runtime.instanceName` scopes the Docker Compose project.
- `runtime.apiPort` controls the local health API port.
- `outputRoot` is where current timeline artifacts are written.

Unknown product-specific settings are preserved by settings updates.

## Input And Output

Provide one ChatGPT export ZIP when you refresh:

```powershell
.\cli.bat items refresh --file C:\path\chatgpt-export.zip --json
```

The source ZIP is not deleted, moved, renamed, or overwritten.

The configured output root contains:

```text
<outputRoot>\
  manifest.json
  <conversation-id>\
    convert_info.json
    timeline.json
```

`items download` creates a handoff ZIP containing `README.md`, `convert_info.json`, and `timeline.json` for the exported conversations.

See [docs/OUTPUTS.md](docs/OUTPUTS.md) for the concrete JSON structure and field meanings.

## Quick Start

```powershell
cd C:\apps\TimelineForChatGPT
.\start.ps1
.\cli.bat settings init
.\cli.bat settings status
.\cli.bat items refresh --file C:\path\chatgpt-export.zip --json
.\cli.bat items list --json
.\cli.bat items download --to C:\path\handoff
```

## Health Check

```powershell
Invoke-RestMethod http://127.0.0.1:19300/health
```

The endpoint returns a JSON boolean: `true` when the settings file is readable and has a valid `outputRoot` / `runtime.apiPort`, otherwise `false`.

Only `GET /health` is part of the local API surface. Item refresh, list, download, and run inspection are CLI operations.

## Supported Item Operations

The supported item commands are:

- `items refresh`: convert one ChatGPT export ZIP.
- `items list`: list generated conversation items.
- `items download`: create a handoff ZIP from generated items.

This product does not provide `items remove`. Source ZIP deletion and generated-data cleanup are outside the current CLI contract.

## Common Commands

```powershell
.\start.ps1
.\stop.ps1

.\cli.bat settings status
.\cli.bat settings output show
.\cli.bat settings output set C:\TimelineData\chatgpt

.\cli.bat items refresh --file C:\path\chatgpt-export.zip --json
.\cli.bat items refresh --file C:\path\chatgpt-export.zip --download-to C:\path\handoff --json
.\cli.bat items list --json
.\cli.bat items list --page 1 --page-size 100 --json
.\cli.bat items download --to C:\path\handoff

.\cli.bat runs list --json
.\cli.bat runs show --run-id <run-id> --json
.\cli.bat config-check
```

## Detailed Docs

- [docs/CLI.md](docs/CLI.md): read this when you need the command contract.
- [docs/OUTPUTS.md](docs/OUTPUTS.md): read this when you need the generated file layout.
- [docs/RUNTIME.md](docs/RUNTIME.md): read this when you need runtime requirements and settings.
- [docs/TESTING.md](docs/TESTING.md): read this when you need validation commands.
