. "$PSScriptRoot\common.ps1"
Set-TimelineForChatGPTRoot
& docker compose run --rm --entrypoint python -e PYTHONPATH=/workspace/worker/src worker -m unittest discover -s /workspace/worker/tests -v
Exit-TimelineForChatGPTNativeCommand
