# TimelineForChatGPT

## What This Product Does

TimelineForChatGPT converts one ChatGPT export ZIP into per-conversation timeline artifacts. It is a local CLI product: the Windows launcher is the normal entrypoint, and the worker runs through Docker Compose.

The output is designed to be easy to inspect, package, and hand off to another Timeline product or an LLM workflow.

## Input

Provide one ChatGPT export ZIP when you refresh:

```powershell
.\cli.bat items refresh --file C:\path\chatgpt-export.zip --json
```

The source ZIP is not deleted, moved, renamed, or overwritten.

## Output

The default output root is:

```text
C:\TimelineData\chatgpt
```

Important generated files:

```text
<outputRoot>\
  manifest.json
  <conversation-id>\
    convert_info.json
    timeline.json
```

`items download` creates a handoff ZIP containing `README.md`, `convert_info.json`, and `timeline.json` for the exported conversations.

## Quick Start

```powershell
cd C:\apps\TimelineForChatGPT
.\cli.bat settings init
.\cli.bat items refresh --file C:\path\chatgpt-export.zip --json
.\cli.bat items list --json
.\cli.bat items download --to C:\path\handoff
```

## Sample

Sample input and sample output are planned. For now, use a real ChatGPT export ZIP stored outside this repository.

## Common Commands

```powershell
.\cli.bat settings status
.\cli.bat settings output show
.\cli.bat settings output set C:\TimelineData\chatgpt

.\cli.bat items refresh --file C:\path\chatgpt-export.zip --json
.\cli.bat items refresh --file C:\path\chatgpt-export.zip --download-to C:\path\handoff --json
.\cli.bat items list --json
.\cli.bat items list --page 1 --page-size 100 --json
.\cli.bat items download --to C:\path\handoff
```

## Detailed Docs

- [docs/CLI.md](docs/CLI.md): read this when you need the command contract.
- [docs/OUTPUTS.md](docs/OUTPUTS.md): read this when you need the generated file layout.
- [docs/PIPELINE.md](docs/PIPELINE.md): read this when you need the processing flow.
- [docs/RUNTIME.md](docs/RUNTIME.md): read this when you need runtime requirements and settings.
- [docs/TESTING.md](docs/TESTING.md): read this when you need validation commands.
- [docs/SAFETY.md](docs/SAFETY.md): read this when you need operational safety notes.
