Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if (-not (Test-Path Variable:global:LASTEXITCODE)) {
    $global:LASTEXITCODE = 0
}

function Set-TimelineForChatGPTRoot {
    Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
}

function Initialize-TimelineForChatGPTWorkspace {
    Set-TimelineForChatGPTRoot
}

function Initialize-TimelineForChatGPTSettings {
    Initialize-TimelineForChatGPTWorkspace
    if (-not (Test-Path -LiteralPath "settings.json")) {
        Copy-Item -LiteralPath "settings.example.json" -Destination "settings.json"
    }
    $settings = Get-Content -LiteralPath "settings.json" -Raw | ConvertFrom-Json
    $outputRoot = [string]$settings.outputRoot
    if ($outputRoot) {
        if (-not [System.IO.Path]::IsPathRooted($outputRoot)) {
            $outputRoot = Join-Path (Get-Location) $outputRoot
        }
        if (-not (Test-Path -LiteralPath $outputRoot)) {
            New-Item -ItemType Directory -Path $outputRoot | Out-Null
        }
        $env:TIMELINE_FOR_CHATGPT_HOST_OUTPUT_ROOT = $outputRoot
    }
}

function Exit-TimelineForChatGPTNativeCommand {
    exit $LASTEXITCODE
}
