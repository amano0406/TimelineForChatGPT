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

function Get-TimelineForChatGPTSettingsPath {
    Initialize-TimelineForChatGPTWorkspace
    $settingsPath = [Environment]::GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_HOST_SETTINGS_PATH", "Process")
    if ([string]::IsNullOrWhiteSpace($settingsPath)) {
        $settingsPath = Join-Path (Get-Location) "settings.json"
    }
    elseif (-not [System.IO.Path]::IsPathRooted($settingsPath)) {
        $settingsPath = Join-Path (Get-Location) $settingsPath
    }
    return [System.IO.Path]::GetFullPath($settingsPath)
}

function Initialize-TimelineForChatGPTSettings {
    Initialize-TimelineForChatGPTWorkspace
    $settingsPath = Get-TimelineForChatGPTSettingsPath
    if (-not (Test-Path -LiteralPath $settingsPath)) {
        $settingsDir = Split-Path -Parent $settingsPath
        if ($settingsDir -and -not (Test-Path -LiteralPath $settingsDir)) {
            New-Item -ItemType Directory -Path $settingsDir | Out-Null
        }
        Copy-Item -LiteralPath "settings.example.json" -Destination $settingsPath
    }
    $settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
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
