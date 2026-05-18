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

function Normalize-TimelineForChatGPTInstanceName {
    param([string]$Value)

    $normalized = ([string]$Value).Trim().ToLowerInvariant()
    $normalized = [System.Text.RegularExpressions.Regex]::Replace($normalized, "[^a-z0-9-]+", "-")
    $normalized = $normalized.Trim("-")
    if ($normalized.Length -gt 48) {
        $normalized = $normalized.Substring(0, 48).Trim("-")
    }
    return $normalized
}

function Get-TimelineForChatGPTRuntimeSettings {
    Initialize-TimelineForChatGPTWorkspace
    $settingsPath = Get-TimelineForChatGPTSettingsPath
    $settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $runtime = if ($settings.PSObject.Properties["runtime"] -and $null -ne $settings.runtime) { $settings.runtime } else { [pscustomobject]@{} }

    $instanceName = ""
    if ($runtime.PSObject.Properties["instanceName"]) {
        $instanceName = Normalize-TimelineForChatGPTInstanceName -Value ([string]$runtime.instanceName)
    }
    $envInstanceName = Normalize-TimelineForChatGPTInstanceName -Value ([Environment]::GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_INSTANCE_NAME", "Process"))
    if ($envInstanceName) {
        $instanceName = $envInstanceName
    }

    $apiPort = 19300
    if ($runtime.PSObject.Properties["apiPort"]) {
        [void][int]::TryParse(([string]$runtime.apiPort), [ref]$apiPort)
    }
    $envApiPort = [Environment]::GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_API_PORT", "Process")
    if (-not [string]::IsNullOrWhiteSpace($envApiPort)) {
        [void][int]::TryParse($envApiPort, [ref]$apiPort)
    }
    if ($apiPort -lt 1 -or $apiPort -gt 65535) {
        $apiPort = 19300
    }

    $composeProject = [Environment]::GetEnvironmentVariable("COMPOSE_PROJECT_NAME", "Process")
    if ([string]::IsNullOrWhiteSpace($composeProject)) {
        $composeProject = [Environment]::GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_COMPOSE_PROJECT", "Process")
    }
    if ([string]::IsNullOrWhiteSpace($composeProject)) {
        $composeProject = if ($instanceName) { "timeline-for-chatgpt-$instanceName" } else { "timeline-for-chatgpt" }
    }

    return [pscustomobject]@{
        InstanceName = $instanceName
        ApiPort = $apiPort
        ComposeProject = $composeProject
    }
}

function Initialize-TimelineForChatGPTSettings {
    Initialize-TimelineForChatGPTWorkspace
    $settingsPath = Get-TimelineForChatGPTSettingsPath
    $env:TIMELINE_FOR_CHATGPT_HOST_SETTINGS_PATH = $settingsPath
    Initialize-TimelineForChatGPTDriveMounts
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
    $runtime = Get-TimelineForChatGPTRuntimeSettings
    if ($runtime.InstanceName) {
        $env:TIMELINE_FOR_CHATGPT_INSTANCE_NAME = [string]$runtime.InstanceName
    }
    $env:TIMELINE_FOR_CHATGPT_API_PORT = [string]$runtime.ApiPort
    $env:TIMELINE_FOR_CHATGPT_COMPOSE_PROJECT = [string]$runtime.ComposeProject
}

function Initialize-TimelineForChatGPTDriveMounts {
    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        return
    }

    Set-TimelineForChatGPTDriveMountDefault -Name "TIMELINE_FOR_CHATGPT_C_DRIVE_MOUNT" -DriveRoot "C:\"
    Set-TimelineForChatGPTDriveMountDefault -Name "TIMELINE_FOR_CHATGPT_F_DRIVE_MOUNT" -DriveRoot "F:\"
}

function Set-TimelineForChatGPTDriveMountDefault {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$DriveRoot
    )

    $current = [Environment]::GetEnvironmentVariable($Name, "Process")
    if (-not [string]::IsNullOrWhiteSpace($current)) {
        return
    }
    if (-not (Test-Path -LiteralPath $DriveRoot)) {
        return
    }
    $resolved = (Resolve-Path -LiteralPath $DriveRoot).Path.Replace('\', '/')
    Set-Item -Path "Env:$Name" -Value $resolved
}

function Get-TimelineForChatGPTDockerCommand {
    $dockerExe = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path -LiteralPath $dockerExe) { return $dockerExe }
    $docker = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($docker) { return $docker.Source }
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if ($docker) { return $docker.Source }
    throw "docker.exe was not found. Install or start Docker Desktop."
}

function Get-TimelineForChatGPTComposeArguments {
    $arguments = [System.Collections.Generic.List[string]]::new()
    $arguments.Add("compose") | Out-Null
    $runtime = Get-TimelineForChatGPTRuntimeSettings
    $arguments.Add("-p") | Out-Null
    $arguments.Add([string]$runtime.ComposeProject) | Out-Null
    return $arguments.ToArray()
}

function Get-TimelineForChatGPTApiBaseUrl {
    Initialize-TimelineForChatGPTSettings
    $runtime = Get-TimelineForChatGPTRuntimeSettings
    return "http://127.0.0.1:$($runtime.ApiPort)"
}

function Invoke-TimelineForChatGPTApi {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [object]$Body = @{}
    )

    $baseUrl = Get-TimelineForChatGPTApiBaseUrl
    $url = $baseUrl.TrimEnd("/") + "/" + $Path.TrimStart("/")
    $json = $Body | ConvertTo-Json -Depth 20 -Compress
    $result = Invoke-RestMethod -Method Post -Uri $url -Body $json -ContentType "application/json"
    $global:LASTEXITCODE = 0
    $result | ConvertTo-Json -Depth 50
}

function Test-TimelineForChatGPTApi {
    $baseUrl = Get-TimelineForChatGPTApiBaseUrl
    $result = Invoke-RestMethod -Method Get -Uri ($baseUrl.TrimEnd("/") + "/health")
    $global:LASTEXITCODE = 0
    $result | ConvertTo-Json -Depth 10
}

function Format-TimelineForChatGPTProcessArgument {
    param([string]$Value)

    if ($null -eq $Value) { return '""' }
    $text = [string]$Value
    if ($text.Length -eq 0) { return '""' }
    if ($text -notmatch '[\s"]') { return $text }

    $builder = [System.Text.StringBuilder]::new()
    [void]$builder.Append('"')
    $backslashes = 0
    foreach ($character in $text.ToCharArray()) {
        if ($character -eq '\') {
            $backslashes += 1
            continue
        }
        if ($character -eq '"') {
            if ($backslashes -gt 0) {
                [void]$builder.Append(('\' * ($backslashes * 2)))
                $backslashes = 0
            }
            [void]$builder.Append('\"')
            continue
        }
        if ($backslashes -gt 0) {
            [void]$builder.Append(('\' * $backslashes))
            $backslashes = 0
        }
        [void]$builder.Append($character)
    }
    if ($backslashes -gt 0) {
        [void]$builder.Append(('\' * ($backslashes * 2)))
    }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Invoke-TimelineForChatGPTHiddenProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [switch]$WriteOutput,
        [switch]$SuppressOutput
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = (@($Arguments) | ForEach-Object { Format-TimelineForChatGPTProcessArgument -Value ([string]$_) }) -join " "
    $startInfo.WorkingDirectory = (Get-Location).Path
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $startInfo.StandardErrorEncoding = [System.Text.UTF8Encoding]::new($false)
    $fileDirectory = Split-Path -Parent $FilePath
    if ($fileDirectory) {
        $currentPath = $startInfo.EnvironmentVariables["PATH"]
        if (-not $currentPath) {
            $currentPath = $env:PATH
        }
        $updatedPath = "$fileDirectory;$currentPath"
        $startInfo.EnvironmentVariables["PATH"] = $updatedPath
        $startInfo.EnvironmentVariables["Path"] = $updatedPath
    }
    $startInfo.EnvironmentVariables["PATHEXT"] = ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.CPL"

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()

    $stdout = [string]$stdoutTask.Result
    $stderr = [string]$stderrTask.Result
    if ($WriteOutput -and -not $SuppressOutput) {
        if ($stdout.Length -gt 0) { [Console]::Out.Write($stdout) }
        if ($stderr.Length -gt 0) { [Console]::Error.Write($stderr) }
    }

    return [pscustomobject]@{
        ExitCode = [int]$process.ExitCode
        Stdout = $stdout
        Stderr = $stderr
    }
}

function Assert-TimelineForChatGPTDockerReady {
    param([Parameter(Mandatory = $true)][string]$Docker)

    $dockerInfo = Invoke-TimelineForChatGPTHiddenProcess -FilePath $Docker -Arguments @("info") -SuppressOutput
    if ($dockerInfo.ExitCode -ne 0) {
        throw "Docker Desktop is installed but the Docker engine is not ready."
    }
}

function Invoke-TimelineForChatGPTWithFileLock {
    param(
        [Parameter(Mandatory = $true)][string]$LockName,
        [Parameter(Mandatory = $true)][scriptblock]$ScriptBlock
    )

    $generatedDir = Join-Path (Get-Location) ".docker"
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

function Exit-TimelineForChatGPTNativeCommand {
    exit $LASTEXITCODE
}
