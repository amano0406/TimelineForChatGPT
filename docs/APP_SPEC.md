# App Spec

## Goal

`TimelineForChatGPT` converts a local ChatGPT export into timeline-oriented text that can be reviewed by a human or handed to an LLM.

The system prioritizes:

- simple ZIP-first input
- readable run output
- local processing
- a product shape close to `video2timeline`

## App Model

- `web`: ASP.NET Core Razor Pages
- `worker`: Python
- coordination: shared filesystem, not worker HTTP calls

## User Flow

1. open the GUI
2. upload one ChatGPT export ZIP
3. create a job
4. open the job detail page
5. inspect the conversation list
6. open a conversation timeline
7. optionally download the ZIP handoff package

## Output Model

Every run writes:

- `request.json`
- `status.json`
- `result.json`
- `manifest.json`
- `RUN_INFO.md`
- `NOTICE.md`
- `export_summary.json`
- `conversation_index.jsonl`

Each conversation currently writes:

- `conversation.json`
- `messages.jsonl`
- `events.jsonl`
- `segments.json`
- `timeline.md`
- `attachments.json`

LLM export writes:

- `llm/conversation_index.jsonl`
- `llm/conversation_corpus-YYYY-MM.jsonl`

## Current scaffold scope

- one ZIP per job
- current-branch-first normalization
- best-effort text extraction
- best-effort timeline rendering
- upload and worker both reject obviously corrupted ZIP files before pretending the export is usable
