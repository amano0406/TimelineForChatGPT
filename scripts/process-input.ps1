param(
    [Parameter(Mandatory = $true)]
    [string] $FileName
)

. "$PSScriptRoot\common.ps1"
Set-TimelineForChatGPTRoot
Invoke-TimelineForChatGPTApi -Path "items/refresh" -Body @{
    file = $FileName
}
Exit-TimelineForChatGPTNativeCommand
