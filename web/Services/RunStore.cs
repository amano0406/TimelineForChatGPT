using System.IO.Compression;
using System.Text;
using System.Text.Json;
using ChatGpt2Timeline.Web.Localization;
using ChatGpt2Timeline.Web.Models;

namespace ChatGpt2Timeline.Web.Services;

public sealed class RunStore(AppPaths paths, SettingsStore settingsStore, UiText text)
{
    private readonly JsonSerializerOptions _jsonOptions = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true,
    };

    public async Task<UploadedFileReference> SaveUploadAsync(
        IFormFile file,
        CancellationToken cancellationToken = default)
    {
        if (file.Length <= 0)
        {
            throw new InvalidOperationException(text["Validation.UploadEmpty"]);
        }

        var safeName = MakeSafeFileName(file.FileName);
        var extension = Path.GetExtension(safeName);
        if (!string.Equals(extension, ".zip", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(text["Validation.OnlyZipSupported"]);
        }

        var uploadFolder = Path.Combine(
            paths.UploadsRoot,
            $"upload-{DateTimeOffset.Now:yyyyMMdd-HHmmss}-{Guid.NewGuid():N}"[..36]);
        Directory.CreateDirectory(uploadFolder);

        var storedFileName = $"0001-{safeName}";
        var storedPath = Path.Combine(uploadFolder, storedFileName);
        await using (var stream = File.Create(storedPath))
        {
            await file.CopyToAsync(stream, cancellationToken);
        }

        ValidateZipArchive(storedPath);

        return new UploadedFileReference
        {
            ReferenceId = $"{Path.GetFileName(uploadFolder)}:{storedFileName}",
            StoredPath = storedPath,
            OriginalName = file.FileName,
            SizeBytes = file.Length,
        };
    }

    public async Task<(string JobId, string RunDirectory)> CreateJobAsync(
        UploadedFileReference uploadedFile,
        bool reprocessDuplicates = false,
        CancellationToken cancellationToken = default)
    {
        var settings = await settingsStore.LoadAsync(cancellationToken);
        var outputRoot = settings.OutputRoots.FirstOrDefault(static root => root.Enabled)
            ?? throw new InvalidOperationException(text["Validation.NoOutputRoot"]);

        Directory.CreateDirectory(paths.AppDataRoot);
        Directory.CreateDirectory(paths.UploadsRoot);
        Directory.CreateDirectory(paths.OutputsRoot);
        Directory.CreateDirectory(outputRoot.Path);

        var jobId = $"job-{DateTimeOffset.Now:yyyyMMdd-HHmmss}-{Guid.NewGuid():N}"[..27];
        var runDir = Path.Combine(outputRoot.Path, jobId);
        Directory.CreateDirectory(runDir);
        Directory.CreateDirectory(Path.Combine(runDir, "conversations"));
        Directory.CreateDirectory(Path.Combine(runDir, "llm"));
        Directory.CreateDirectory(Path.Combine(runDir, "logs"));

        var request = new JobRequestDocument
        {
            SchemaVersion = 1,
            JobId = jobId,
            CreatedAt = DateTimeOffset.UtcNow.ToString("O"),
            OutputRootId = outputRoot.Id,
            OutputRootPath = outputRoot.Path,
            Profile = "timeline-default",
            ReprocessDuplicates = reprocessDuplicates,
            ParserOptions = new ParserOptionsDocument(),
            InputItems =
            [
                new InputItemDocument
                {
                    InputId = "upload-0001",
                    SourceKind = "upload_zip",
                    SourceId = "uploads",
                    OriginalPath = uploadedFile.OriginalName,
                    DisplayName = uploadedFile.OriginalName,
                    SizeBytes = uploadedFile.SizeBytes,
                    UploadedPath = uploadedFile.StoredPath,
                },
            ],
        };

        var status = new JobStatusDocument
        {
            SchemaVersion = 1,
            JobId = jobId,
            State = "pending",
            CurrentStage = "queued",
            Message = "Queued for worker pickup.",
            UpdatedAt = DateTimeOffset.UtcNow.ToString("O"),
        };

        var result = new JobResultDocument
        {
            SchemaVersion = 1,
            JobId = jobId,
            State = "pending",
            RunDir = runDir,
            OutputRootId = outputRoot.Id,
            OutputRootPath = outputRoot.Path,
        };

        var manifest = new ManifestDocument
        {
            SchemaVersion = 1,
            JobId = jobId,
            GeneratedAt = DateTimeOffset.UtcNow.ToString("O"),
        };

        await WriteJsonAsync(Path.Combine(runDir, "request.json"), request, cancellationToken);
        await WriteJsonAsync(Path.Combine(runDir, "status.json"), status, cancellationToken);
        await WriteJsonAsync(Path.Combine(runDir, "result.json"), result, cancellationToken);
        await WriteJsonAsync(Path.Combine(runDir, "manifest.json"), manifest, cancellationToken);
        await File.WriteAllTextAsync(
            Path.Combine(runDir, "RUN_INFO.md"),
            "# Run Info\n\nPending worker pickup.\n",
            Encoding.UTF8,
            cancellationToken);
        await File.WriteAllTextAsync(
            Path.Combine(runDir, "NOTICE.md"),
            "# Notice\n\nThis scaffold currently supports one ChatGPT export ZIP per job.\n",
            Encoding.UTF8,
            cancellationToken);

        return (jobId, runDir);
    }

    public async Task<IReadOnlyList<RunSummary>> ListRunsAsync(CancellationToken cancellationToken = default)
    {
        var settings = await settingsStore.LoadAsync(cancellationToken);
        var outputRoot = settings.OutputRoots.FirstOrDefault(static root => root.Enabled);
        if (outputRoot is null || !Directory.Exists(outputRoot.Path))
        {
            return [];
        }

        var rows = new List<RunSummary>();
        foreach (var runDir in Directory.EnumerateDirectories(outputRoot.Path, "job-*", SearchOption.TopDirectoryOnly)
                     .OrderByDescending(static value => value, StringComparer.OrdinalIgnoreCase))
        {
            cancellationToken.ThrowIfCancellationRequested();
            var request = await ReadJsonAsync<JobRequestDocument>(Path.Combine(runDir, "request.json"), cancellationToken);
            var status = await ReadJsonAsync<JobStatusDocument>(Path.Combine(runDir, "status.json"), cancellationToken);
            var result = await ReadJsonAsync<JobResultDocument>(Path.Combine(runDir, "result.json"), cancellationToken);
            if (request is null || status is null)
            {
                continue;
            }

            rows.Add(new RunSummary
            {
                JobId = request.JobId,
                RunDirectory = runDir,
                State = status.State,
                CurrentStage = status.CurrentStage,
                ConversationsTotal = status.ConversationsTotal,
                ConversationsDone = status.ConversationsDone,
                ConversationsSkipped = status.ConversationsSkipped,
                ConversationsFailed = status.ConversationsFailed,
                TotalSizeBytes = request.InputItems.Sum(static item => item.SizeBytes),
                ProgressPercent = status.ProgressPercent,
                EstimatedRemainingSec = status.EstimatedRemainingSec,
                CreatedAt = request.CreatedAt,
                HasDownloadableArchive = !string.IsNullOrWhiteSpace(result?.ArchivePath) && File.Exists(result!.ArchivePath!),
            });
        }

        return rows;
    }

    public async Task<RunSummary?> GetActiveRunAsync(CancellationToken cancellationToken = default)
    {
        var runs = await ListRunsAsync(cancellationToken);
        return runs.FirstOrDefault(static run => string.Equals(run.State, "running", StringComparison.OrdinalIgnoreCase))
            ?? runs.FirstOrDefault(static run => string.Equals(run.State, "pending", StringComparison.OrdinalIgnoreCase));
    }

    public async Task<RunDetails?> GetRunDetailsAsync(string jobId, CancellationToken cancellationToken = default)
    {
        var runDir = await FindRunDirectoryAsync(jobId, cancellationToken);
        if (runDir is null)
        {
            return null;
        }

        var request = await ReadJsonAsync<JobRequestDocument>(Path.Combine(runDir, "request.json"), cancellationToken);
        var status = await ReadJsonAsync<JobStatusDocument>(Path.Combine(runDir, "status.json"), cancellationToken);
        var result = await ReadJsonAsync<JobResultDocument>(Path.Combine(runDir, "result.json"), cancellationToken);
        var manifest = await ReadJsonAsync<ManifestDocument>(Path.Combine(runDir, "manifest.json"), cancellationToken);
        var exportSummary = await ReadJsonAsync<ExportSummaryDocument>(Path.Combine(runDir, "export_summary.json"), cancellationToken);
        var conversations = await ReadJsonLinesAsync<ConversationSummaryDocument>(
            Path.Combine(runDir, "conversation_index.jsonl"),
            cancellationToken);

        return new RunDetails
        {
            JobId = jobId,
            RunDirectory = runDir,
            Request = request,
            Status = status,
            Result = result,
            Manifest = manifest,
            ExportSummary = exportSummary,
            Conversations = conversations,
            LogTail = await ReadLogTailAsync(Path.Combine(runDir, "logs", "worker.log"), cancellationToken),
        };
    }

    public async Task<ConversationDetails?> GetConversationDetailsAsync(
        string jobId,
        string conversationId,
        CancellationToken cancellationToken = default)
    {
        var runDir = await FindRunDirectoryAsync(jobId, cancellationToken);
        if (runDir is null)
        {
            return null;
        }

        var conversations = await ReadJsonLinesAsync<ConversationSummaryDocument>(
            Path.Combine(runDir, "conversation_index.jsonl"),
            cancellationToken);
        var summary = conversations.FirstOrDefault(item =>
            string.Equals(item.ConversationId, conversationId, StringComparison.OrdinalIgnoreCase));
        if (summary is null)
        {
            return null;
        }

        var conversationDir = Path.Combine(runDir, "conversations", conversationId);
        var timelinePath = Path.Combine(conversationDir, "timeline.md");
        var conversationJsonPath = Path.Combine(conversationDir, "conversation.json");
        var timelineMarkdown = File.Exists(timelinePath)
            ? await File.ReadAllTextAsync(timelinePath, cancellationToken)
            : $"# {text["Page.Details.Timeline"]}\n\n{text["Validation.TimelinePending"]}\n";

        return new ConversationDetails
        {
            JobId = jobId,
            ConversationId = conversationId,
            Title = summary.Title,
            CreateTime = summary.CreateTime,
            UpdateTime = summary.UpdateTime,
            StartedAtUtc = summary.StartedAtUtc,
            EndedAtUtc = summary.EndedAtUtc,
            DefaultModelSlug = summary.DefaultModelSlug,
            MessageCountTotal = summary.MessageCountTotal,
            MainBranchMessageCount = summary.MainBranchMessageCount,
            BranchCount = summary.BranchCount,
            AttachmentCount = summary.AttachmentCount,
            ImageCount = summary.ImageCount,
            AudioCount = summary.AudioCount,
            ToolCount = summary.ToolCount,
            HasToolMessages = summary.HasToolMessages,
            HasSystemMessages = summary.HasSystemMessages,
            HasAttachments = summary.HasAttachments,
            HasMultimodalContent = summary.HasMultimodalContent,
            RoleCountsTotal = summary.RoleCountsTotal,
            ContentTypeCountsTotal = summary.ContentTypeCountsTotal,
            MainBranchRoleCounts = summary.MainBranchRoleCounts,
            MainBranchContentTypeCounts = summary.MainBranchContentTypeCounts,
            TimelineMarkdown = timelineMarkdown,
            TimelinePath = timelinePath,
            ConversationJsonPath = conversationJsonPath,
        };
    }

    public async Task<string?> BuildRunArchiveAsync(string jobId, CancellationToken cancellationToken = default)
    {
        var details = await GetRunDetailsAsync(jobId, cancellationToken);
        var archivePath = details?.Result?.ArchivePath;
        if (string.IsNullOrWhiteSpace(archivePath) || !File.Exists(archivePath))
        {
            return null;
        }

        return archivePath;
    }

    private async Task<string?> FindRunDirectoryAsync(string jobId, CancellationToken cancellationToken)
    {
        var settings = await settingsStore.LoadAsync(cancellationToken);
        var outputRoot = settings.OutputRoots.FirstOrDefault(static root => root.Enabled);
        if (outputRoot is null)
        {
            return null;
        }

        var candidate = Path.Combine(outputRoot.Path, jobId);
        return Directory.Exists(candidate) ? candidate : null;
    }

    private async Task WriteJsonAsync<T>(string path, T payload, CancellationToken cancellationToken)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        await File.WriteAllTextAsync(
            path,
            JsonSerializer.Serialize(payload, _jsonOptions),
            Encoding.UTF8,
            cancellationToken);
    }

    private async Task<T?> ReadJsonAsync<T>(string path, CancellationToken cancellationToken)
    {
        if (!File.Exists(path))
        {
            return default;
        }

        await using var stream = File.OpenRead(path);
        return await JsonSerializer.DeserializeAsync<T>(stream, _jsonOptions, cancellationToken);
    }

    private async Task<IReadOnlyList<T>> ReadJsonLinesAsync<T>(string path, CancellationToken cancellationToken)
    {
        if (!File.Exists(path))
        {
            return [];
        }

        var rows = new List<T>();
        foreach (var line in await File.ReadAllLinesAsync(path, cancellationToken))
        {
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            var row = JsonSerializer.Deserialize<T>(line, _jsonOptions);
            if (row is not null)
            {
                rows.Add(row);
            }
        }

        return rows;
    }

    private static async Task<string> ReadLogTailAsync(string path, CancellationToken cancellationToken)
    {
        if (!File.Exists(path))
        {
            return "";
        }

        var lines = await File.ReadAllLinesAsync(path, cancellationToken);
        return string.Join(
            Environment.NewLine,
            lines.Skip(Math.Max(0, lines.Length - 200)));
    }

    private static string MakeSafeFileName(string name)
    {
        var invalid = Path.GetInvalidFileNameChars();
        var builder = new StringBuilder(name.Length);
        foreach (var character in name)
        {
            builder.Append(invalid.Contains(character) ? '-' : character);
        }

        return builder.ToString();
    }

    private void ValidateZipArchive(string path)
    {
        try
        {
            using var archive = ZipFile.OpenRead(path);
            if (archive.Entries.Count == 0)
            {
                throw new InvalidOperationException(text["Validation.ZipEmpty"]);
            }
        }
        catch (Exception ex) when (ex is InvalidDataException or IOException)
        {
            try
            {
                File.Delete(path);
            }
            catch
            {
                // Keep the original validation error if cleanup fails.
            }

            throw new InvalidOperationException(
                text["Validation.ZipUnreadable"],
                ex);
        }
    }
}
