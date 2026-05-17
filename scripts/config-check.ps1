. "$PSScriptRoot\common.ps1"
Set-TimelineForChatGPTRoot
Test-TimelineForChatGPTApi
Invoke-TimelineForChatGPTApi -Path "settings/status" -Body @{}
Exit-TimelineForChatGPTNativeCommand
