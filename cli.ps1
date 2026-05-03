[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
Set-Location $repoRoot

function Get-TfcgDockerCommand {
    $dockerExe = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path -LiteralPath $dockerExe) { return $dockerExe }
    $docker = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($docker) { return $docker.Source }
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($docker) { return $docker.Source }
    throw "docker.exe was not found. Install or start Docker Desktop."
}

function Get-TfcgConfiguredOutputRoot {
    $settingsPath = Join-Path $repoRoot "settings.json"
    if (-not (Test-Path -LiteralPath $settingsPath)) {
        return $null
    }
    $settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
    $outputRoot = [string]$settings.outputRoot
    if (-not $outputRoot) {
        return $null
    }
    if (-not [System.IO.Path]::IsPathRooted($outputRoot)) {
        $outputRoot = Join-Path $repoRoot $outputRoot
    }
    return [System.IO.Path]::GetFullPath($outputRoot)
}

function Initialize-TfcgSettingsFile {
    $settingsPath = Join-Path $repoRoot "settings.json"
    if (-not (Test-Path -LiteralPath $settingsPath)) {
        Copy-Item -LiteralPath (Join-Path $repoRoot "settings.example.json") -Destination $settingsPath
    }
    $outputRoot = Get-TfcgConfiguredOutputRoot
    if ($outputRoot) {
        if (-not (Test-Path -LiteralPath $outputRoot)) {
            New-Item -ItemType Directory -Path $outputRoot | Out-Null
        }
    }
}

function Show-TfcgUsage {
    Write-Host "TimelineForChatGPT CLI"
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  .\cli.bat settings init"
    Write-Host "  .\cli.bat settings status"
    Write-Host "  .\cli.bat settings output show"
    Write-Host "  .\cli.bat settings output set C:\TimelineData\chatgpt"
    Write-Host "  .\cli.bat items refresh --file C:\path\chatgpt-export.zip --json"
    Write-Host "  .\cli.bat items refresh --file C:\path\chatgpt-export.zip --download-to C:\path\handoff --json"
    Write-Host "  .\cli.bat items list --json"
    Write-Host "  .\cli.bat items list --page 1 --page-size 100 --json"
    Write-Host "  .\cli.bat items download --to C:\path\handoff"
    Write-Host "  .\cli.bat runs list --json"
    Write-Host "  .\cli.bat runs show --run-id <run-id> --json"
}

function Test-TfcgContainerPath {
    param([string]$Value)
    return $Value.StartsWith("/")
}

function Resolve-TfcgHostPath {
    param(
        [string]$Value,
        [bool]$RequireExisting
    )
    $candidate = $Value
    if (-not [System.IO.Path]::IsPathRooted($candidate)) {
        $candidate = Join-Path $repoRoot $candidate
    }
    if ($RequireExisting) {
        return (Resolve-Path -LiteralPath $candidate).Path
    }
    return [System.IO.Path]::GetFullPath($candidate)
}

function Get-TfcgLastExitCode {
    $variable = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    if ($variable -and $null -ne $variable.Value) {
        return [int]$variable.Value
    }
    if ($?) { return 0 }
    return 1
}

function Invoke-TfcgDocker {
    param(
        [string]$Docker,
        [string[]]$Arguments
    )
    & $Docker @Arguments
    $exitCode = Get-TfcgLastExitCode
    if ($exitCode -ne 0) {
        throw "docker command failed with exit code ${exitCode}: docker $($Arguments -join ' ')"
    }
}

function Start-TfcgComposeWorker {
    param([string]$Docker)
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Docker compose up -d --remove-orphans worker *> $null
        $exitCode = Get-TfcgLastExitCode
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0) {
        throw "docker compose up failed with exit code ${exitCode}."
    }
    $containerId = (& $Docker compose ps -q worker).Trim()
    if (-not $containerId) {
        throw "TimelineForChatGPT worker container was not found after docker compose up."
    }
    return $containerId
}

function Invoke-TfcgWithFileLock {
    param(
        [Parameter(Mandatory = $true)][string]$LockName,
        [Parameter(Mandatory = $true)][scriptblock]$ScriptBlock
    )

    $generatedDir = Join-Path $repoRoot ".docker"
    New-Item -ItemType Directory -Path $generatedDir -Force | Out-Null
    $lockPath = Join-Path $generatedDir $LockName
    $lockStream = $null
    for ($attempt = 1; $attempt -le 300; $attempt += 1) {
        try {
            $lockStream = [System.IO.File]::Open(
                $lockPath,
                [System.IO.FileMode]::OpenOrCreate,
                [System.IO.FileAccess]::ReadWrite,
                [System.IO.FileShare]::None
            )
            break
        }
        catch [System.IO.IOException] {
            Start-Sleep -Milliseconds 100
        }
    }
    if (-not $lockStream) {
        throw "Timed out waiting for lock: $lockPath"
    }

    try {
        & $ScriptBlock
    }
    finally {
        if ($lockStream) {
            $lockStream.Dispose()
        }
    }
}

function New-TfcgContainerTempRoot {
    param([string]$Kind)
    $token = [guid]::NewGuid().ToString("N")
    return "/shared/cache/timeline-for-chatgpt/$Kind/cli-$token"
}

function New-TfcgSafeContainerFileName {
    param([string]$Name)
    $safe = [System.IO.Path]::GetFileName($Name)
    if (-not $safe) { return "input.zip" }
    $safe = $safe.Replace("\", "_").Replace("/", "_").Replace(":", "_")
    if ($safe.Length -le 80) {
        return $safe
    }

    $extension = [System.IO.Path]::GetExtension($safe)
    if (-not $extension) { $extension = ".bin" }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($safe)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") }) -join ""
    } finally {
        $sha.Dispose()
    }
    return "input-$($hash.Substring(0, 16))$extension"
}

function Copy-TfcgInputToContainer {
    param(
        [string]$Docker,
        [string]$ContainerId,
        [string]$HostPath
    )
    $root = New-TfcgContainerTempRoot -Kind "uploads"
    $leaf = New-TfcgSafeContainerFileName -Name $HostPath
    $containerPath = "$root/$leaf"
    Invoke-TfcgDocker -Docker $Docker -Arguments @("exec", $ContainerId, "mkdir", "-p", $root)
    Invoke-TfcgDocker -Docker $Docker -Arguments @("cp", $HostPath, "${ContainerId}:$containerPath")
    return [PSCustomObject]@{
        ContainerPath = $containerPath
        TempRoot = $root
    }
}

function Convert-TfcgArgsForManagedWorker {
    param(
        [string[]]$InputArgs,
        [string]$Docker,
        [string]$ContainerId
    )

    $containerArgs = New-Object System.Collections.Generic.List[string]
    $tempRoots = New-Object System.Collections.Generic.List[string]
    $outputPlans = New-Object System.Collections.Generic.List[object]
    $overwrite = $InputArgs -contains "--overwrite"

    for ($i = 0; $i -lt $InputArgs.Count; $i++) {
        $arg = $InputArgs[$i]
        if ($arg -eq "--file" -and $i + 1 -lt $InputArgs.Count) {
            $rawPath = $InputArgs[$i + 1]
            $containerArgs.Add($arg)
            if (Test-TfcgContainerPath $rawPath) {
                $containerArgs.Add($rawPath)
            } else {
                $hostPath = Resolve-TfcgHostPath -Value $rawPath -RequireExisting $true
                $copy = Copy-TfcgInputToContainer -Docker $Docker -ContainerId $ContainerId -HostPath $hostPath
                $containerArgs.Add([string]$copy.ContainerPath)
                $tempRoots.Add([string]$copy.TempRoot)
            }
            $i++
            continue
        }

        if (($arg -eq "--download-to" -or $arg -eq "--to") -and $i + 1 -lt $InputArgs.Count) {
            $rawPath = $InputArgs[$i + 1]
            $containerArgs.Add($arg)
            if (Test-TfcgContainerPath $rawPath) {
                $containerArgs.Add($rawPath)
            } else {
                $hostPath = Resolve-TfcgHostPath -Value $rawPath -RequireExisting $false
                $containerRoot = New-TfcgContainerTempRoot -Kind "handoff"
                Invoke-TfcgDocker -Docker $Docker -Arguments @("exec", $ContainerId, "mkdir", "-p", $containerRoot)
                $isZip = [System.IO.Path]::GetExtension($hostPath).ToLowerInvariant() -eq ".zip"
                if ($isZip) {
                    $hostDir = Split-Path -Parent $hostPath
                    if (-not (Test-Path -LiteralPath $hostDir)) {
                        New-Item -ItemType Directory -Path $hostDir | Out-Null
                    }
                    if ((Test-Path -LiteralPath $hostPath) -and -not $overwrite) {
                        throw "Download target already exists: $hostPath"
                    }
                    $containerPath = "$containerRoot/$(New-TfcgSafeContainerFileName -Name $hostPath)"
                } else {
                    if (-not (Test-Path -LiteralPath $hostPath)) {
                        New-Item -ItemType Directory -Path $hostPath | Out-Null
                    }
                    $containerPath = $containerRoot
                }
                $containerArgs.Add($containerPath)
                $tempRoots.Add($containerRoot)
                $outputPlans.Add(
                    [PSCustomObject]@{
                        HostPath = $hostPath
                        ContainerPath = $containerPath
                        ContainerRoot = $containerRoot
                        IsZip = $isZip
                        Overwrite = $overwrite
                    }
                )
            }
            $i++
            continue
        }

        $containerArgs.Add($arg)
    }

    return [PSCustomObject]@{
        ContainerArgs = [string[]]$containerArgs
        TempRoots = [string[]]$tempRoots
        OutputPlans = [object[]]$outputPlans
    }
}

function Copy-TfcgOutputsFromContainer {
    param(
        [string]$Docker,
        [string]$ContainerId,
        [object[]]$OutputPlans
    )
    $replacements = @{}
    foreach ($plan in $OutputPlans) {
        if ($plan.IsZip) {
            Invoke-TfcgDocker -Docker $Docker -Arguments @("cp", "${ContainerId}:$($plan.ContainerPath)", $plan.HostPath)
            $replacements[[string]$plan.ContainerPath] = [string]$plan.HostPath
            continue
        }

        $zipPaths = @(& $Docker exec $ContainerId find $plan.ContainerPath -maxdepth 1 -type f -name "*.zip" -print)
        $exitCode = Get-TfcgLastExitCode
        if ($exitCode -ne 0) {
            throw "Failed to inspect container output directory: $($plan.ContainerPath)"
        }
        foreach ($zipPath in $zipPaths) {
            $zipName = [System.IO.Path]::GetFileName([string]$zipPath)
            $hostZipPath = Join-Path $plan.HostPath $zipName
            if ((Test-Path -LiteralPath $hostZipPath) -and -not $plan.Overwrite) {
                throw "Download target already exists: $hostZipPath"
            }
            $replacements[[string]$zipPath] = [string]$hostZipPath
        }
        Invoke-TfcgDocker -Docker $Docker -Arguments @("cp", "${ContainerId}:$($plan.ContainerPath)/.", $plan.HostPath)
    }
    return $replacements
}

function Remove-TfcgContainerTempRoots {
    param(
        [string]$Docker,
        [string]$ContainerId,
        [string[]]$TempRoots
    )
    foreach ($root in $TempRoots) {
        if ($root) {
            & $Docker exec $ContainerId rm -rf $root *> $null
        }
    }
}

function Write-TfcgCommandOutput {
    param(
        [object[]]$CommandOutput,
        [hashtable]$Replacements
    )
    $text = ($CommandOutput | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
    $trimmed = $text.TrimStart()
    $jsonLike = $trimmed.StartsWith("{") -or $trimmed.StartsWith("[")
    foreach ($key in ($Replacements.Keys | Sort-Object { ([string]$_).Length } -Descending)) {
        $value = [string]$Replacements[$key]
        if ($jsonLike) {
            $value = $value.Replace("\", "\\")
        }
        $text = $text.Replace([string]$key, $value)
    }
    if ($text.Length -gt 0) {
        Write-Output $text
    }
}

if ($null -eq $CliArgs -or $CliArgs.Count -eq 0) {
    Show-TfcgUsage
    exit 0
}

Initialize-TfcgSettingsFile
$hostOutputRoot = Get-TfcgConfiguredOutputRoot
if ($hostOutputRoot) {
    $env:TIMELINE_FOR_CHATGPT_HOST_OUTPUT_ROOT = $hostOutputRoot
}
$docker = Get-TfcgDockerCommand
& $docker info *> $null
if (-not $?) {
    throw "Docker Desktop is installed but the Docker engine is not ready."
}

$script:TfcgExitCode = 0
$script:TfcgCommandOutput = @()
$script:TfcgReplacements = @{}

Invoke-TfcgWithFileLock -LockName "docker-compose.lock" -ScriptBlock {
    $containerId = Start-TfcgComposeWorker -Docker $docker
    $converted = Convert-TfcgArgsForManagedWorker -InputArgs $CliArgs -Docker $docker -ContainerId $containerId
    $replacements = @{}
    if ($hostOutputRoot) {
        $replacements["/workspace/output/"] = ([string]$hostOutputRoot).TrimEnd("\") + "\"
        $replacements["/workspace/output"] = $hostOutputRoot
    }

    try {
        $dockerArgs = @("compose", "exec", "-T", "worker", "python", "-m", "timeline_for_chatgpt_worker") + $converted.ContainerArgs
        if ($env:TIMELINE_FOR_CHATGPT_DEBUG_CLI -eq "1") {
            Write-Host "CliArgs=$($CliArgs -join '|')"
            Write-Host "DockerArgs=$($dockerArgs -join '|')"
        }
        $script:TfcgCommandOutput = & $docker @dockerArgs 2>&1
        $script:TfcgExitCode = Get-TfcgLastExitCode
        if ($script:TfcgExitCode -eq 0 -and $converted.OutputPlans.Count -gt 0) {
            $outputReplacements = Copy-TfcgOutputsFromContainer -Docker $docker -ContainerId $containerId -OutputPlans $converted.OutputPlans
            foreach ($key in $outputReplacements.Keys) {
                $replacements[[string]$key] = [string]$outputReplacements[$key]
            }
        }
    } finally {
        Remove-TfcgContainerTempRoots -Docker $docker -ContainerId $containerId -TempRoots $converted.TempRoots
    }
    $script:TfcgReplacements = $replacements
}

Write-TfcgCommandOutput -CommandOutput $script:TfcgCommandOutput -Replacements $script:TfcgReplacements
exit $script:TfcgExitCode
