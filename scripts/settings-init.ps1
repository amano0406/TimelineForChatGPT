. "$PSScriptRoot\common.ps1"
Initialize-TimelineForChatGPTWorkspace
& docker compose run --rm worker settings init @args
Exit-TimelineForChatGPTNativeCommand
