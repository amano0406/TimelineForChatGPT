. "$PSScriptRoot\common.ps1"
Set-TimelineForChatGPTRoot
& (Join-Path $PSScriptRoot "..\cli.ps1") items refresh @args
Exit-TimelineForChatGPTNativeCommand
