param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RefreshArgs
)

. "$PSScriptRoot\common.ps1"
Set-TimelineForChatGPTRoot
$body = @{}
for ($index = 0; $index -lt $RefreshArgs.Count; $index += 1) {
    $name = [string]$RefreshArgs[$index]
    $next = if ($index + 1 -lt $RefreshArgs.Count) { [string]$RefreshArgs[$index + 1] } else { "" }
    switch ($name) {
        "--file" {
            if ([string]::IsNullOrWhiteSpace($next)) { throw "--file requires a path." }
            $body["file"] = $next
            $index += 1
        }
        "--download-to" {
            if ([string]::IsNullOrWhiteSpace($next)) { throw "--download-to requires a path." }
            $body["downloadTo"] = $next
            $index += 1
        }
        "--json" {
        }
        default {
            throw "Unsupported API refresh argument: $name"
        }
    }
}
Invoke-TimelineForChatGPTApi -Path "items/refresh" -Body $body
Exit-TimelineForChatGPTNativeCommand
