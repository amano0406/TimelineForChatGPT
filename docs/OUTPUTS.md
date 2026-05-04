# Outputs

[Back to README](../README.md)

## Output Root

The default output root is:

```text
C:\TimelineData\chatgpt
```

Each refresh rebuilds the current output from the supplied ZIP.

## Current Output Layout

```text
<outputRoot>\
  manifest.json
  <conversation-id>\
    convert_info.json
    timeline.json
```

## `manifest.json`

`manifest.json` is the top-level index for the current output. It includes the run id, generated time, item count, source ZIP name, and conversation item rows.

## `convert_info.json`

`convert_info.json` contains conversion metadata for one conversation.

## `timeline.json`

`timeline.json` contains the conversation timeline data for one conversation. It preserves message order, role, timestamp fields when available, final exported title, and message text.

## Handoff ZIP

`items download --to` creates a ZIP for handoff. The ZIP contains:

```text
README.md
items/<conversation-id>/convert_info.json
items/<conversation-id>/timeline.json
```

Binary attachment files are not included in the handoff ZIP.
