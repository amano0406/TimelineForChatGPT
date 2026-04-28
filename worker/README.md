# TimelineForChatGPT worker

Local Python worker that polls pending jobs, parses ChatGPT export ZIP files, and writes timeline-oriented outputs.

## Direct CLI

Refresh configured input directories:

```bash
PYTHONPATH=src python3 -m timeline_for_chatgpt_worker refresh
```

The latest human-readable refresh summary is written as `refresh-latest.md` in the configured output root.
The stable known-input catalog is written as `index.md` and `index.json` in the same output root.

Validate the config without processing:

```bash
PYTHONPATH=src python3 -m timeline_for_chatgpt_worker config-check
```

Process one file directly:

```bash
PYTHONPATH=src python3 -m timeline_for_chatgpt_worker process /path/to/chatgpt-export.zip --output-root /tmp/timelineforchatgpt-outputs
```

The command creates one run directory, processes the export, and prints the run directory path.
