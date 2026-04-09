# Normalized Event Alignment

## Purpose

`video2timeline` and `TimelineForChatGPT` should be different parsers that converge on a similar downstream shape.

The best place to align them is the normalized event layer.

## Current Reality

The two tools do not produce the same raw event rows today.

### `video2timeline`

Its normalized timeline is derived from:

- transcript segments
- timestamps from the original media
- screen observations
- screen change summaries

The important unit is a time-bounded media segment.

### `TimelineForChatGPT`

Its current scaffold writes:

- `messages.jsonl`
  - branch-filtered message rows
- `events.jsonl`
  - event-envelope rows derived from those messages
- `segments.json`
  - turn-like groups over the selected path

The important source unit is still a message on the selected conversation path,
but downstream outputs are now shaped more like an event/segment pipeline.

## Alignment Principle

The tools do not need identical parsers.
They do need a compatible event vocabulary.

The useful shared mental model is:

1. source-specific parser
2. normalized events
3. grouped segments
4. timeline markdown
5. LLM handoff pack

The main difference is only step 1.

## Proposed Shared Event Envelope

This is the convergence target for downstream tooling.

Required common fields:

- `source_type`
- `source_unit_id`
- `event_id`
- `start_at_utc`
- `end_at_utc`
- `actor`
- `kind`
- `text`
- `artifacts`
- `payload`

Recommended semantics:

- `source_type`
  - `video`
  - `chatgpt_export`
- `source_unit_id`
  - media id or conversation id
- `event_id`
  - stable identifier inside the unit
- `start_at_utc` / `end_at_utc`
  - true event time when known
  - for media-derived relative time, downstream renderers may also carry relative offsets in `payload`
- `actor`
  - `user`
  - `assistant`
  - `speaker`
  - `system`
  - `tool`
  - `observer`
- `kind`
  - `message`
  - `speech`
  - `screen`
  - `screen_change`
  - `attachment`
  - `tool_call`
  - `tool_result`
- `text`
  - main human-readable text body
- `artifacts`
  - file references, frame captures, or attachment pointers
- `payload`
  - source-specific structured detail that should not be flattened away

## Mapping By Tool

### `video2timeline` -> common envelope

- transcript segment
  - `actor = speaker`
  - `kind = speech`
- OCR / screen note
  - `actor = observer`
  - `kind = screen`
- diff summary
  - `actor = observer`
  - `kind = screen_change`

### `TimelineForChatGPT` -> common envelope

- user or assistant message
  - `actor = role`
  - `kind = message`
- system row
  - `actor = system`
  - `kind = message`
- tool row
  - `actor = tool`
  - `kind = tool_result`
- attachment reference
  - stays in `artifacts`
  - may optionally emit a companion `attachment` event later

## Segment Alignment

Segments are the next layer above events.

The grouping rule differs by source:

- `video2timeline`
  - group nearby transcript and screen context by time range
- `TimelineForChatGPT`
  - group one or more adjacent messages by conversation flow

But the segment contract can still converge on:

- `segment_id`
- `source_unit_id`
- `start_at_utc`
- `end_at_utc`
- `title`
- `summary`
- `event_ids[]`

## Current `TimelineForChatGPT` Status

Right now the scaffold keeps these distinctions:

- `messages.jsonl`
  - branch-selected message rows
- `events.jsonl`
  - event-envelope rows derived from those messages
- `segments.json`
  - lightweight turn groups built from the main-branch events

That is acceptable for MVP.
The important point is to treat it as an interim shared model, not the final one.

## What To Keep Source-specific

These details should stay in `payload`, not the shared top-level keys.

### `video2timeline`

- speaker confidence
- OCR engine output
- screen hash deltas
- frame file paths
- diarization metadata

### `TimelineForChatGPT`

- `message_id`
- `parent_message_id`
- `content_type`
- `model_slug`
- branch metadata
- raw attachment ids
- ChatGPT-specific metadata blobs

## Rule For Future Work

When adding new timeline tools, do not start from file names.
Start from the event envelope.

The test should be:

- can this source be normalized into events and segments?
- can it render `timeline.md`?
- can it produce a compact index and ZIP?

If yes, it belongs in the same family even if the parser is completely different.
