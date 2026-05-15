. "$PSScriptRoot\common.ps1"
Initialize-TimelineForChatGPTSettings
$docker = Get-TimelineForChatGPTDockerCommand
$composeArgs = Get-TimelineForChatGPTComposeArguments
$buildArgs = @($composeArgs) + @("build", "worker", "api")
& $docker @buildArgs
Exit-TimelineForChatGPTNativeCommand
