. "$PSScriptRoot\common.ps1"
Set-TimelineForChatGPTRoot
& docker compose build worker
Exit-TimelineForChatGPTNativeCommand
