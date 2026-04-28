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
    foreach ($path in @("data\inputs", "data\outputs", "data\state")) {
        if (-not (Test-Path -LiteralPath $path)) {
            New-Item -ItemType Directory -Path $path | Out-Null
        }
    }
}

function Initialize-TimelineForChatGPTSettings {
    Initialize-TimelineForChatGPTWorkspace
    if (-not (Test-Path -LiteralPath "settings.json")) {
        & docker compose run --rm worker settings init
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
}

function Exit-TimelineForChatGPTNativeCommand {
    exit $LASTEXITCODE
}
