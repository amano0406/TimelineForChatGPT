param(
    [string]$RepoRoot = "C:\apps\TimelineForChatGPT",
    [string]$WorkspaceRoot = "C:\Codex\workspaces\TimelineForChatGPT-e2e",
    [string]$FixtureSourceRoot = "C:\Codex\workspaces\TimelineForChatGPT-smoke\export",
    [int]$Port = 5092,
    [switch]$KeepWorkspace
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
    param([string]$Message)
    Write-Host "[TimelineForChatGPT:e2e] $Message"
}

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Assert-Contains {
    param(
        [string]$Text,
        [string]$Needle,
        [string]$Message
    )

    if (-not $Text.Contains($Needle)) {
        throw "$Message Missing: $Needle"
    }
}

function Ensure-Directory {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Get-DotnetLauncher {
    $dotnetCommand = Get-Command dotnet -ErrorAction SilentlyContinue
    if ($dotnetCommand) {
        return $dotnetCommand.Source
    }

    $fallbackPath = "C:\Program Files\dotnet\dotnet.exe"
    if (Test-Path -LiteralPath $fallbackPath) {
        return $fallbackPath
    }

    throw "dotnet was not found in PATH and fallback launcher was not present."
}

function Remove-DirectoryIfExists {
    param([string]$Path)

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Get-FileTextUtf8 {
    param([string]$Path)
    return Get-Content -LiteralPath $Path -Encoding UTF8 -Raw
}

function New-HttpSessionContext {
    Add-Type -AssemblyName System.Net.Http

    $cookieContainer = New-Object System.Net.CookieContainer
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.CookieContainer = $cookieContainer
    $handler.AllowAutoRedirect = $false

    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(30)

    return @{
        Client = $client
        Handler = $handler
    }
}

function Write-HttpResponseArtifacts {
    param(
        [System.Net.Http.HttpResponseMessage]$Response,
        [string]$HeadersPath,
        [string]$BodyPath
    )

    $headerLines = [System.Collections.Generic.List[string]]::new()
    $headerLines.Add(("HTTP/{0} {1} {2}" -f $Response.Version, [int]$Response.StatusCode, $Response.ReasonPhrase))

    foreach ($header in $Response.Headers) {
        foreach ($value in $header.Value) {
            $headerLines.Add(("{0}: {1}" -f $header.Key, $value))
        }
    }

    foreach ($header in $Response.Content.Headers) {
        foreach ($value in $header.Value) {
            $headerLines.Add(("{0}: {1}" -f $header.Key, $value))
        }
    }

    [System.IO.File]::WriteAllText($HeadersPath, ($headerLines -join [Environment]::NewLine), [System.Text.Encoding]::UTF8)
    $body = $Response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    [System.IO.File]::WriteAllText($BodyPath, $body, [System.Text.Encoding]::UTF8)
}

function New-GoodFixtureZip {
    param(
        [string]$SourceRoot,
        [string]$TargetPath
    )

    Assert-True (Test-Path -LiteralPath $SourceRoot) "Fixture source root not found: $SourceRoot"
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    if (Test-Path -LiteralPath $TargetPath) {
        Remove-Item -LiteralPath $TargetPath -Force
    }

    $requiredFiles = @(
        "export_manifest.json",
        "conversations-000.json"
    )
    $optionalFiles = @(
        "analysis_summary.json"
    )

    $archive = [System.IO.Compression.ZipFile]::Open($TargetPath, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($name in $requiredFiles) {
            $sourcePath = Join-Path $SourceRoot $name
            Assert-True (Test-Path -LiteralPath $sourcePath) "Missing required fixture source file: $sourcePath"
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive,
                $sourcePath,
                $name,
                [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
        }

        foreach ($name in $optionalFiles) {
            $sourcePath = Join-Path $SourceRoot $name
            if (Test-Path -LiteralPath $sourcePath) {
                [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                    $archive,
                    $sourcePath,
                    $name,
                    [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
            }
        }
    }
    finally {
        $archive.Dispose()
    }

    Assert-True ((Get-Item -LiteralPath $TargetPath).Length -gt 0) "Failed to build good fixture ZIP."
}

function New-BadFixtureZip {
    param(
        [string]$GoodZipPath,
        [string]$BadZipPath
    )

    $bytes = [System.IO.File]::ReadAllBytes($GoodZipPath)
    Assert-True ($bytes.Length -gt 4096) "Good fixture ZIP is too small to truncate safely."

    $targetLength = [Math]::Max(2048, $bytes.Length - 2048)
    $stream = [System.IO.File]::Open($BadZipPath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
    try {
        $stream.Write($bytes, 0, $targetLength)
    }
    finally {
        $stream.Dispose()
    }
}

function Wait-ForHealth {
    param(
        [string]$BaseUrl,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/health" -TimeoutSec 3
            if ($response.StatusCode -eq 200) {
                return
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }

    throw "Timed out waiting for web health endpoint: $BaseUrl/health"
}

function Download-Page {
    param(
        [string]$Url,
        [string]$TargetPath
    )

    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 30
    [System.IO.File]::WriteAllText($TargetPath, $response.Content, [System.Text.Encoding]::UTF8)
}

function Get-RequestVerificationToken {
    param([string]$HtmlPath)

    $html = Get-FileTextUtf8 -Path $HtmlPath
    $match = [regex]::Match($html, 'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"')
    Assert-True $match.Success "Could not find __RequestVerificationToken in $HtmlPath"
    return $match.Groups[1].Value
}

function Submit-Job {
    param(
        [string]$BaseUrl,
        [string]$ZipPath,
        [string]$ArtifactRoot,
        [string]$Culture = "en"
    )

    $newJobHeaders = Join-Path $ArtifactRoot ("new-job-" + [System.IO.Path]::GetFileNameWithoutExtension($ZipPath) + ".headers.txt")
    $newJobHtml = Join-Path $ArtifactRoot ("new-job-" + [System.IO.Path]::GetFileNameWithoutExtension($ZipPath) + ".html")
    $postHeaders = Join-Path $ArtifactRoot ("post-job-" + [System.IO.Path]::GetFileNameWithoutExtension($ZipPath) + ".headers.txt")
    $postHtml = Join-Path $ArtifactRoot ("post-job-" + [System.IO.Path]::GetFileNameWithoutExtension($ZipPath) + ".html")
    $newJobUrl = "$BaseUrl/jobs/new?culture=$Culture&ui-culture=$Culture"

    $session = New-HttpSessionContext
    $multipartContent = $null
    $stream = $null

    try {
        $getResponse = $session.Client.GetAsync($newJobUrl).GetAwaiter().GetResult()
        Write-HttpResponseArtifacts -Response $getResponse -HeadersPath $newJobHeaders -BodyPath $newJobHtml
        $token = Get-RequestVerificationToken -HtmlPath $newJobHtml

        $multipartContent = New-Object System.Net.Http.MultipartFormDataContent
        $multipartContent.Add((New-Object System.Net.Http.StringContent($token)), "__RequestVerificationToken")
        $multipartContent.Add((New-Object System.Net.Http.StringContent("false")), "ReprocessDuplicates")

        $stream = [System.IO.File]::OpenRead($ZipPath)
        $fileContent = New-Object System.Net.Http.StreamContent($stream)
        $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("application/zip")
        $multipartContent.Add($fileContent, "UploadFile", [System.IO.Path]::GetFileName($ZipPath))

        $postResponse = $session.Client.PostAsync($newJobUrl, $multipartContent).GetAwaiter().GetResult()
        Write-HttpResponseArtifacts -Response $postResponse -HeadersPath $postHeaders -BodyPath $postHtml

        $location = if ($postResponse.Headers.Location) { $postResponse.Headers.Location.OriginalString } else { $null }
        $jobId = $null
        if ($location) {
            $jobMatch = [regex]::Match($location, '/jobs/(?<id>[^/?\r\n]+)')
            if ($jobMatch.Success) {
                $jobId = $jobMatch.Groups["id"].Value
            }
        }
    }
    finally {
        if ($stream) {
            $stream.Dispose()
        }
        if ($multipartContent) {
            $multipartContent.Dispose()
        }
        $session.Client.Dispose()
        $session.Handler.Dispose()
    }

    return @{
        JobId = $jobId
        RedirectLocation = $location
        HeadersPath = $postHeaders
        ResponseHtmlPath = $postHtml
    }
}

function Get-JsonObject {
    param([string]$Path)
    return (Get-FileTextUtf8 -Path $Path | ConvertFrom-Json)
}

function Invoke-WorkerRunOnce {
    param(
        [string]$RepoRoot,
        [string]$AppDataRoot,
        [string]$UploadsRoot,
        [string]$OutputsRoot
    )

    $pythonLauncher = "C:\Codex\tools\python\codex_python.cmd"
    if (-not (Test-Path -LiteralPath $pythonLauncher)) {
        $pythonLauncher = "py"
    }

    $env:TIMELINE_FOR_CHATGPT_RUNTIME_DEFAULTS = Join-Path $RepoRoot "configs\runtime.defaults.json"
    $env:TIMELINE_FOR_CHATGPT_APPDATA_ROOT = $AppDataRoot
    $env:TIMELINE_FOR_CHATGPT_UPLOADS_ROOT = $UploadsRoot
    $env:TIMELINE_FOR_CHATGPT_OUTPUTS_ROOT = $OutputsRoot
    $env:PYTHONPATH = Join-Path $RepoRoot "worker\src"
    $workerExitCode = 0

    if ($pythonLauncher -eq "py") {
        & py -3 -m timeline_for_chatgpt_worker run-once
    }
    else {
        & $pythonLauncher -m timeline_for_chatgpt_worker run-once
    }

    if (Test-Path variable:LASTEXITCODE) {
        $workerExitCode = $LASTEXITCODE
    }
    if ($workerExitCode -ne 0) {
        throw "Worker run-once failed with exit code $workerExitCode"
    }
}

function Get-FirstConversationId {
    param([string]$RunDir)

    $indexPath = Join-Path $RunDir "conversation_index.jsonl"
    Assert-True (Test-Path -LiteralPath $indexPath) "Conversation index not found: $indexPath"
    $firstLine = Get-Content -LiteralPath $indexPath -Encoding UTF8 -TotalCount 1
    Assert-True (-not [string]::IsNullOrWhiteSpace($firstLine)) "Conversation index is empty: $indexPath"
    return (($firstLine | ConvertFrom-Json).conversation_id)
}

function Assert-GoodRun {
    param(
        [string]$BaseUrl,
        [string]$OutputsRoot,
        [string]$JobId,
        [string]$ArtifactRoot
    )

    $runDir = Join-Path $OutputsRoot $JobId
    $statusPath = Join-Path $runDir "status.json"
    $resultPath = Join-Path $runDir "result.json"
    $deadline = (Get-Date).AddSeconds(10)
    $status = $null
    $result = $null

    while ((Get-Date) -lt $deadline) {
        $status = Get-JsonObject -Path $statusPath
        $result = Get-JsonObject -Path $resultPath
        if ($status.state -eq "completed" -and $result.state -eq "completed") {
            break
        }
        Start-Sleep -Milliseconds 250
    }

    Assert-True ($status.state -eq "completed") "Good fixture run did not complete."
    Assert-True ($result.state -eq "completed") "Good fixture result did not complete."
    Assert-True (Test-Path -LiteralPath (Join-Path $runDir "export_summary.json")) "Missing export_summary.json"
    Assert-True (Test-Path -LiteralPath (Join-Path $runDir "conversation_index.jsonl")) "Missing conversation_index.jsonl"
    Assert-True (Test-Path -LiteralPath (Join-Path $runDir "$JobId.zip")) "Missing archive ZIP"

    $conversationId = Get-FirstConversationId -RunDir $runDir
    $conversationDir = Join-Path $runDir ("conversations\" + $conversationId)
    $eventsPath = Join-Path $conversationDir "events.jsonl"
    $segmentsPath = Join-Path $conversationDir "segments.json"
    Assert-True (Test-Path -LiteralPath $eventsPath) "Missing conversation events.jsonl"
    Assert-True (Test-Path -LiteralPath $segmentsPath) "Missing conversation segments.json"

    $firstEventLine = Get-Content -LiteralPath $eventsPath -Encoding UTF8 -TotalCount 1
    Assert-Contains -Text $firstEventLine -Needle '"source_type": "chatgpt_export"' -Message "Event output is not using the normalized envelope."

    $segments = Get-JsonObject -Path $segmentsPath
    Assert-True ($segments.items.Count -ge 1) "Segments file is empty."
    Assert-True ($segments.items[0].event_ids.Count -ge 1) "First segment has no event ids."

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archivePath = Join-Path $runDir "$JobId.zip"
    $archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
    try {
        $entryNames = @($archive.Entries | ForEach-Object { $_.FullName })
        Assert-True ($entryNames -contains "conversation_index.jsonl") "Archive is missing conversation_index.jsonl"
        Assert-True ($entryNames -contains "conversations/$conversationId/events.jsonl") "Archive is missing structured conversation events."
        Assert-True ($entryNames -contains "conversations/$conversationId/segments.json") "Archive is missing structured conversation segments."
    }
    finally {
        $archive.Dispose()
    }

    $jobsEn = Join-Path $ArtifactRoot "jobs-en.html"
    $jobsJa = Join-Path $ArtifactRoot "jobs-ja.html"
    $detailsEn = Join-Path $ArtifactRoot "details-en.html"
    $detailsJa = Join-Path $ArtifactRoot "details-ja.html"
    $conversationEn = Join-Path $ArtifactRoot "conversation-en.html"
    $conversationJa = Join-Path $ArtifactRoot "conversation-ja.html"

    Download-Page -Url "$BaseUrl/jobs?culture=en&ui-culture=en" -TargetPath $jobsEn
    Download-Page -Url "$BaseUrl/jobs?culture=ja&ui-culture=ja" -TargetPath $jobsJa
    Download-Page -Url "$BaseUrl/jobs/${JobId}?culture=en&ui-culture=en" -TargetPath $detailsEn
    Download-Page -Url "$BaseUrl/jobs/${JobId}?culture=ja&ui-culture=ja" -TargetPath $detailsJa
    Download-Page -Url "$BaseUrl/jobs/${JobId}/conversations/${conversationId}?culture=en&ui-culture=en" -TargetPath $conversationEn
    Download-Page -Url "$BaseUrl/jobs/${JobId}/conversations/${conversationId}?culture=ja&ui-culture=ja" -TargetPath $conversationJa

    $jobsEnText = Get-FileTextUtf8 -Path $jobsEn
    $jobsJaText = Get-FileTextUtf8 -Path $jobsJa
    $detailsEnText = Get-FileTextUtf8 -Path $detailsEn
    $detailsJaText = Get-FileTextUtf8 -Path $detailsJa
    $conversationEnText = Get-FileTextUtf8 -Path $conversationEn
    $conversationJaText = Get-FileTextUtf8 -Path $conversationJa

    Assert-Contains -Text $jobsEnText -Needle "<html lang=""en"">" -Message "English jobs page is not localized."
    Assert-Contains -Text $jobsEnText -Needle "Recent Jobs" -Message "English jobs page is missing its title."
    Assert-Contains -Text $jobsJaText -Needle "&#x30B8;&#x30E7;&#x30D6;" -Message "Japanese jobs page is missing its title."
    Assert-Contains -Text $jobsJaText -Needle "&#x65B0;&#x898F;&#x30B8;&#x30E7;&#x30D6;" -Message "Japanese jobs page is missing the new job label."

    Assert-Contains -Text $detailsEnText -Needle "Job Details" -Message "English details page is missing its title."
    Assert-Contains -Text $detailsEnText -Needle "Download ZIP" -Message "English details page is missing download text."
    Assert-Contains -Text $detailsJaText -Needle "&#x30A8;&#x30AF;&#x30B9;&#x30DD;&#x30FC;&#x30C8;&#x6982;&#x8981;" -Message "Japanese details page is missing export summary text."
    Assert-Contains -Text $detailsJaText -Needle "&#x30EF;&#x30FC;&#x30AB;&#x30FC;&#x30ED;&#x30B0;" -Message "Japanese details page is missing worker log text."

    Assert-Contains -Text $conversationEnText -Needle "Conversation" -Message "English conversation page is missing its title."
    Assert-Contains -Text $conversationEnText -Needle "Metadata" -Message "English conversation page is missing metadata text."
    Assert-Contains -Text $conversationJaText -Needle "&#x30C4;&#x30FC;&#x30EB;&#x30E1;&#x30C3;&#x30BB;&#x30FC;&#x30B8;&#x6570;" -Message "Japanese conversation page is missing tool count text."
    Assert-Contains -Text $conversationJaText -Needle "&#x30ED;&#x30FC;&#x30EB;&#x4EF6;&#x6570;" -Message "Japanese conversation page is missing role count text."

    return $conversationId
}

function Assert-BadUploadRejected {
    param([hashtable]$Submission)

    Assert-True ([string]::IsNullOrWhiteSpace($Submission.JobId)) "Corrupted ZIP unexpectedly created a job."
    $html = Get-FileTextUtf8 -Path $Submission.ResponseHtmlPath
    Assert-Contains -Text $html -Needle "The uploaded ZIP could not be opened." -Message "Corrupted ZIP upload was not rejected."
}

$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$WorkspaceRoot = $WorkspaceRoot
$FixtureSourceRoot = (Resolve-Path -LiteralPath $FixtureSourceRoot).Path
$BaseUrl = "http://127.0.0.1:$Port"

$runtimeRoot = Join-Path $WorkspaceRoot "runtime"
$fixtureRoot = Join-Path $WorkspaceRoot "fixtures"
$artifactRoot = Join-Path $WorkspaceRoot "artifacts"
$buildRoot = Join-Path $runtimeRoot "build"
$appDataRoot = Join-Path $runtimeRoot "app-data"
$uploadsRoot = Join-Path $runtimeRoot "uploads"
$outputsRoot = Join-Path $runtimeRoot "outputs"
$logsRoot = Join-Path $runtimeRoot "logs"
$webBuildRoot = Join-Path $buildRoot "web"
$webBaseOutputRoot = Join-Path $webBuildRoot "bin\"
$webBaseIntermediateRoot = Join-Path $webBuildRoot "obj\"
$goodZip = Join-Path $fixtureRoot "sample-good-export.zip"
$badZip = Join-Path $fixtureRoot "sample-bad-export.zip"
$webStdout = Join-Path $logsRoot "web.stdout.log"
$webStderr = Join-Path $logsRoot "web.stderr.log"

if (-not $KeepWorkspace) {
    Remove-DirectoryIfExists -Path $WorkspaceRoot
}

Ensure-Directory -Path $WorkspaceRoot
Ensure-Directory -Path $runtimeRoot
Ensure-Directory -Path $fixtureRoot
Ensure-Directory -Path $artifactRoot
Ensure-Directory -Path $buildRoot
Ensure-Directory -Path $appDataRoot
Ensure-Directory -Path $uploadsRoot
Ensure-Directory -Path $outputsRoot
Ensure-Directory -Path $logsRoot
Ensure-Directory -Path $webBuildRoot

Write-Step "Building small fixture ZIPs from $FixtureSourceRoot"
New-GoodFixtureZip -SourceRoot $FixtureSourceRoot -TargetPath $goodZip
New-BadFixtureZip -GoodZipPath $goodZip -BadZipPath $badZip

Write-Step "Building ASP.NET Core web app"
Remove-DirectoryIfExists -Path (Join-Path $RepoRoot "web\obj")
$dotnetLauncher = Get-DotnetLauncher
Push-Location (Join-Path $RepoRoot "web")
try {
    $buildExitCode = 0
    & $dotnetLauncher build `
        "/p:UseAppHost=false" `
        "/p:BaseOutputPath=$webBaseOutputRoot" `
        "/p:BaseIntermediateOutputPath=$webBaseIntermediateRoot"
    if (Test-Path variable:LASTEXITCODE) {
        $buildExitCode = $LASTEXITCODE
    }
    if (-not $?) {
        throw "dotnet build failed."
    }
    if ($buildExitCode -ne 0) {
        throw "dotnet build failed with exit code $buildExitCode"
    }
}
finally {
    Pop-Location
}

$env:ASPNETCORE_URLS = $BaseUrl
$env:TIMELINE_FOR_CHATGPT_RUNTIME_DEFAULTS = Join-Path $RepoRoot "configs\runtime.defaults.json"
$env:TIMELINE_FOR_CHATGPT_APPDATA_ROOT = $appDataRoot
$env:TIMELINE_FOR_CHATGPT_UPLOADS_ROOT = $uploadsRoot
$env:TIMELINE_FOR_CHATGPT_OUTPUTS_ROOT = $outputsRoot

$webProcess = $null
$webProjectPath = Join-Path $RepoRoot "web\TimelineForChatGPT.Web.csproj"
try {
    Write-Step "Starting web server on $BaseUrl"
    $webProcess = Start-Process `
        -FilePath $dotnetLauncher `
        -ArgumentList @("run", "--no-launch-profile", "--project", $webProjectPath) `
        -WorkingDirectory (Join-Path $RepoRoot "web") `
        -RedirectStandardOutput $webStdout `
        -RedirectStandardError $webStderr `
        -PassThru

    Wait-ForHealth -BaseUrl $BaseUrl -TimeoutSeconds 30

    Write-Step "Submitting good fixture through /jobs/new"
    $goodSubmission = Submit-Job -BaseUrl $BaseUrl -ZipPath $goodZip -ArtifactRoot $artifactRoot -Culture "en"
    Assert-True (-not [string]::IsNullOrWhiteSpace($goodSubmission.JobId)) "Good fixture did not create a job."
    Write-Step "Running worker for good fixture"
    Invoke-WorkerRunOnce -RepoRoot $RepoRoot -AppDataRoot $appDataRoot -UploadsRoot $uploadsRoot -OutputsRoot $outputsRoot
    $goodConversationId = Assert-GoodRun -BaseUrl $BaseUrl -OutputsRoot $outputsRoot -JobId $goodSubmission.JobId -ArtifactRoot $artifactRoot

    Write-Step "Submitting corrupted fixture through /jobs/new"
    $badSubmission = Submit-Job -BaseUrl $BaseUrl -ZipPath $badZip -ArtifactRoot $artifactRoot -Culture "en"
    Assert-BadUploadRejected -Submission $badSubmission

    $report = [ordered]@{
        base_url = $BaseUrl
        workspace_root = $WorkspaceRoot
        good_fixture = $goodZip
        bad_fixture = $badZip
        good_job_id = $goodSubmission.JobId
        bad_job_id = $badSubmission.JobId
        good_conversation_id = $goodConversationId
        good_run_dir = (Join-Path $outputsRoot $goodSubmission.JobId)
        bad_run_dir = if ($badSubmission.JobId) { Join-Path $outputsRoot $badSubmission.JobId } else { $null }
    }

    $reportPath = Join-Path $WorkspaceRoot "report.json"
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Step "E2E smoke passed. Report: $reportPath"
}
finally {
    if ($null -ne $webProcess -and -not $webProcess.HasExited) {
        Write-Step "Stopping web server PID $($webProcess.Id)"
        Stop-Process -Id $webProcess.Id -Force
    }
}
