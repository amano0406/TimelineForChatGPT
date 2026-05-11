# Outputs

[Back to README](../README.md)

The default output root is:

```text
C:\TimelineData\chatgpt
```

`items refresh --file` rebuilds the current output from the supplied ZIP.

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

## Processing Summary

The worker extracts the ChatGPT export ZIP, locates `conversations.json` or `conversations-*.json`, follows each exported conversation path, and writes normalized conversation items to the current output root.

ZIP-level failures stop the refresh. Conversation-level failures are recorded without changing the source ZIP.
