. "$PSScriptRoot\common.ps1"
Set-TimelineForChatGPTRoot
& (Join-Path $PSScriptRoot "..\cli.ps1") config-check @args
Exit-TimelineForChatGPTNativeCommand
