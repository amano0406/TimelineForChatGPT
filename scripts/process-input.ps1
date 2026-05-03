param(
    [Parameter(Mandatory = $true)]
    [string] $FileName
)

. "$PSScriptRoot\common.ps1"
Set-TimelineForChatGPTRoot
& (Join-Path $PSScriptRoot "..\cli.ps1") items refresh --file $FileName
Exit-TimelineForChatGPTNativeCommand
