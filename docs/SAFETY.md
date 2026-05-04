# Safety

[Back to README](../README.md)

## Source ZIP

The source ChatGPT export ZIP is treated as input only. The CLI does not delete, move, rename, or overwrite it.

## Local Processing

Processing is local and Docker-managed.

## Output Rebuild

`items refresh --file` rebuilds the current output root from the supplied ZIP. Keep important previous output packages separately if you need to preserve them.

## Attachments

Attachment references may appear in generated metadata, but binary attachment files are not copied into the handoff ZIP.

## Existing Files

Download commands do not overwrite an existing ZIP unless `--overwrite` is passed.
