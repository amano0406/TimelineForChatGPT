. "$PSScriptRoot\common.ps1"
Set-TimelineForChatGPTRoot
Write-Error "Directory refresh dry-run is not part of the current TimelineForChatGPT workflow. Use .\cli.ps1 items refresh --file <ChatGPT-export.zip>."
exit 2
