. "$PSScriptRoot\common.ps1"
Initialize-TimelineForChatGPTSettings
& docker compose run --rm worker refresh --dry-run @args
Exit-TimelineForChatGPTNativeCommand
