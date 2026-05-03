. "$PSScriptRoot\common.ps1"
Set-TimelineForChatGPTRoot
& (Join-Path $PSScriptRoot "..\cli.ps1") settings init @args
Exit-TimelineForChatGPTNativeCommand
