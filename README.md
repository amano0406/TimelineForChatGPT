# TimelineForChatGPT

## What This Product Does

TimelineForChatGPT converts one ChatGPT export ZIP into per-conversation timeline artifacts. It is a local Windows product with a small API for Timeline integration, and the conversion worker runs through Docker Compose.

The output is designed to be easy to inspect, package, and hand off to another Timeline product or an LLM workflow.

`start.ps1` starts a Docker worker container that also serves the local API used by Timeline for product actions.

## Runtime

```powershell
cd C:\apps\TimelineForChatGPT
.\start.ps1
```

`start.ps1` starts the Compose-managed `worker` service. The worker hosts the Python conversion code and the local HTTP API.

Run from macOS or Linux:

```bash
./start.sh
```

The bash launcher starts the same Compose-managed worker service. If
`settings.json` still contains a Windows-style `outputRoot`, the launcher uses
`./output` as the host output directory so Docker Desktop on macOS/Linux can
start with a valid bind mount.

Stop the services without deleting generated data:

```powershell
.\stop.ps1
```

On macOS or Linux:

```bash
./stop.sh
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
- `runtime.apiPort` controls the local API port.
- `outputRoot` is where current timeline artifacts are written.

Unknown product-specific settings are preserved by settings updates.

## Input And Output

Provide one ChatGPT export ZIP when you refresh:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/refresh -Body '{"file":"C:\\path\\chatgpt-export.zip"}' -ContentType 'application/json'
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

`POST /items/download` creates a handoff ZIP containing `README.md`, `convert_info.json`, and `timeline.json` for the exported conversations.

See [docs/OUTPUTS.md](docs/OUTPUTS.md) for the concrete JSON structure and field meanings.

## Quick Start

```powershell
cd C:\apps\TimelineForChatGPT
.\start.ps1
Invoke-RestMethod http://127.0.0.1:19300/health
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/settings/status -Body '{}' -ContentType 'application/json'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/refresh -Body '{"file":"C:\\path\\chatgpt-export.zip"}' -ContentType 'application/json'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/list -Body '{}' -ContentType 'application/json'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/download -Body '{"to":"C:\\path\\handoff"}' -ContentType 'application/json'
```

## Local API

```powershell
Invoke-RestMethod http://127.0.0.1:19300/health
```

The endpoint returns a JSON boolean. A successful response means the worker API is reachable.

Supported API routes:

- `GET /health`
- `POST /items/refresh`
- `POST /items/list`
- `POST /items/detail`
- `POST /items/download`
- `POST /settings/status`
- `POST /settings/init`

These routes are served by the resident Python worker container. API calls do
not call host launchers, do not start Docker implicitly, and do not spawn a
separate Python process for each request.

## Supported Item API Actions

The supported item API actions are:

- `POST /items/refresh`: convert one ChatGPT export ZIP.
- `POST /items/list`: list generated conversation items.
- `POST /items/detail`: read one generated conversation timeline for detail preview.
- `POST /items/download`: create a handoff ZIP from generated items.

This product does not provide `POST /items/remove`. Source ZIP deletion and generated-data cleanup are outside the current API contract.

## Common API Calls

```powershell
.\start.ps1
.\stop.ps1

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/settings/status -Body '{}' -ContentType 'application/json'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/refresh -Body '{"file":"C:\\path\\chatgpt-export.zip"}' -ContentType 'application/json'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/list -Body '{"page":1,"pageSize":100}' -ContentType 'application/json'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:19300/items/download -Body '{"to":"C:\\path\\handoff"}' -ContentType 'application/json'
```

## Detailed Docs

- [docs/OUTPUTS.md](docs/OUTPUTS.md): read this when you need the generated file layout.
- [docs/RUNTIME.md](docs/RUNTIME.md): read this when you need runtime requirements and settings.
- [docs/TESTING.md](docs/TESTING.md): read this when you need validation commands.
