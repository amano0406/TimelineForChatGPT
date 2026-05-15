. "$PSScriptRoot\common.ps1"
Initialize-TimelineForChatGPTSettings
$docker = Get-TimelineForChatGPTDockerCommand
$composeArgs = Get-TimelineForChatGPTComposeArguments
$upArgs = @($composeArgs) + @("up", "worker")
& $docker @upArgs
Exit-TimelineForChatGPTNativeCommand
