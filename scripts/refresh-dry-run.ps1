. "$PSScriptRoot\common.ps1"
Set-TimelineForChatGPTRoot
Write-Error "Directory refresh dry-run is not part of the current TimelineForChatGPT workflow. Use POST /items/refresh with a ChatGPT export ZIP path."
exit 2
