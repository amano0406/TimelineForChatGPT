# chatgpt2timeline

Local-first tool that turns ChatGPT export ZIP files into timeline-oriented outputs, with a product shape intentionally close to `video2timeline`.

## Current scaffold scope

- `web`: ASP.NET Core Razor Pages
- `worker`: Python
- `docker-compose.yml`: `web` + `worker`
- job flow:
  - `/jobs/new`
  - `/jobs`
  - `/jobs/{id}`
- worker output:
  - `export_summary.json`
  - `conversation_index.jsonl`
  - `conversations/<id>/timeline.md`
  - `llm/conversation_index.jsonl`
  - `llm/conversation_corpus-YYYY-MM.jsonl`
  - `job-....zip`

## Current limitations

- primary input is one ChatGPT export ZIP per job
- chunked upload is not implemented yet
- extracted directory input is not implemented yet
- timeline rendering is still a best-effort scaffold parser
- older ChatGPT export downloads can be corrupted; the scaffold now rejects ZIP files that cannot be opened cleanly

## Local development

```bash
docker compose up --build
```

Default web URL:

- [http://localhost:8088](http://localhost:8088)

## E2E smoke

There is now a local smoke-style E2E runner that exercises:

- `/jobs/new` multipart ZIP upload
- worker `run-once`
- successful run output
- corrupted ZIP failure
- English and Japanese UI text checks

PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\apps\chatgpt2timeline\tools\e2e\run-smoke.ps1
```

Bash / WSL:

```bash
/mnt/c/apps/chatgpt2timeline/tools/e2e/run-smoke.sh
```

More detail:

- [docs/E2E.md](docs/E2E.md)

## Sample validation note

The local Downloads folder already contained both valid and invalid ChatGPT export ZIP files.

- valid sample:
  - `9885dfc7ffd231544e4fe7922328af9e8b5a7a460a97254226bfea15a748bd2f-2026-03-08-16-36-29-e0ba4a3a358d4d50bbb6b8c0dcacace2.zip`
- invalid samples:
  - `9885dfc7ffd231544e4fe7922328af9e8b5a7a460a97254226bfea15a748bd2f-2026-04-01-09-27-26-8fdebf5afe87415fb7acc1ba11d6e3d1.zip`
  - `-09-27-26-8fdebf5afe87415fb7acc1ba11d6e3d1 (1).zip`
  - `aaa.zip`
  - `first.zip`
  - `second.zip`

Those invalid files still start with a ZIP local header, but they miss the end-of-central-directory record and fail with `BadZipFile`.

## Repo layout

```text
configs/
docker/
docs/
web/
worker/
```
