param(
    [Parameter(Mandatory = $true)]
    [string] $FileName
)

. "$PSScriptRoot\common.ps1"
Initialize-TimelineForChatGPTSettings
& docker compose run --rm worker process "/workspace/data/inputs/$FileName" --output-root /workspace/data/outputs
Exit-TimelineForChatGPTNativeCommand
