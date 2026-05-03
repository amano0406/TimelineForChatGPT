# TimelineForChatGPT worker

Python worker that parses one ChatGPT export ZIP and writes per-conversation output artifacts.

## Docker CLI

From the repo root, prefer the Windows PowerShell entrypoints:

```powershell
.\cli.ps1 settings status
.\cli.ps1 items refresh --file C:\path\chatgpt-export.zip --json
.\cli.ps1 items download --to C:\path\handoff
.\scripts\test.ps1
```

For WSL and non-Windows shells, use Docker Compose directly as the backdoor path.

Refresh the output from one export ZIP:

```bash
docker compose up -d worker
container_id="$(docker compose ps -q worker)"
docker exec "$container_id" mkdir -p /tmp/timeline-for-chatgpt/uploads/manual
docker cp /mnt/c/path/chatgpt-export.zip "$container_id:/tmp/timeline-for-chatgpt/uploads/manual/chatgpt-export.zip"
docker compose exec -T worker python -m timeline_for_chatgpt_worker items refresh --file /tmp/timeline-for-chatgpt/uploads/manual/chatgpt-export.zip --json
```

The source ZIP is not copied into the repo. Upload staging is copied through the Docker `cache-data` volume and removed after the CLI command completes.
The configured output root is bind-mounted and persistent; run/state history and cache use Docker named volumes.

Validate the config without processing:

```bash
docker compose exec -T worker python -m timeline_for_chatgpt_worker config-check
```

Build a handoff ZIP from the current output:

```bash
container_id="$(docker compose ps -q worker)"
docker compose exec -T worker python -m timeline_for_chatgpt_worker items download --to /tmp/timeline-for-chatgpt/handoff/manual
docker cp "$container_id:/tmp/timeline-for-chatgpt/handoff/manual/." /mnt/c/path/handoff
```

The handoff ZIP contains `README.md`, `items/<conversation-id>/convert_info.json`, and `items/<conversation-id>/timeline.json`.

Host Python CLI execution is intentionally blocked for normal operation. Set `TIMELINE_FOR_CHATGPT_ALLOW_HOST_CLI=1` only for tests.
