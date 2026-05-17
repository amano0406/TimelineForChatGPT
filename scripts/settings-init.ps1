. "$PSScriptRoot\common.ps1"
Set-TimelineForChatGPTRoot
Invoke-TimelineForChatGPTApi -Path "settings/init" -Body @{}
Exit-TimelineForChatGPTNativeCommand
