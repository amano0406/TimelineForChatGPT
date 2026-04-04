using System.Text.Json.Serialization;

namespace ChatGpt2Timeline.Web.Models;

public sealed class RootOption
{
    [JsonPropertyName("id")]
    public string Id { get; set; } = "";

    [JsonPropertyName("displayName")]
    public string DisplayName { get; set; } = "";

    [JsonPropertyName("path")]
    public string Path { get; set; } = "";

    [JsonPropertyName("enabled")]
    public bool Enabled { get; set; } = true;
}

public sealed class AppSettingsDocument
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; set; } = 1;

    [JsonPropertyName("inputRoots")]
    public List<RootOption> InputRoots { get; set; } = [];

    [JsonPropertyName("outputRoots")]
    public List<RootOption> OutputRoots { get; set; } = [];

    [JsonPropertyName("allowedExtensions")]
    public List<string> AllowedExtensions { get; set; } = [];
}

public sealed class UploadedFileReference
{
    [JsonPropertyName("referenceId")]
    public string ReferenceId { get; set; } = "";

    [JsonPropertyName("storedPath")]
    public string StoredPath { get; set; } = "";

    [JsonPropertyName("originalName")]
    public string OriginalName { get; set; } = "";

    [JsonPropertyName("sizeBytes")]
    public long SizeBytes { get; set; }
}

public sealed class InputItemDocument
{
    [JsonPropertyName("input_id")]
    public string InputId { get; set; } = "";

    [JsonPropertyName("source_kind")]
    public string SourceKind { get; set; } = "";

    [JsonPropertyName("source_id")]
    public string SourceId { get; set; } = "";

    [JsonPropertyName("original_path")]
    public string OriginalPath { get; set; } = "";

    [JsonPropertyName("display_name")]
    public string DisplayName { get; set; } = "";

    [JsonPropertyName("size_bytes")]
    public long SizeBytes { get; set; }

    [JsonPropertyName("uploaded_path")]
    public string? UploadedPath { get; set; }
}

public sealed class ParserOptionsDocument
{
    [JsonPropertyName("follow_current_node_only")]
    public bool FollowCurrentNodeOnly { get; set; } = true;

    [JsonPropertyName("include_tool_messages")]
    public bool IncludeToolMessages { get; set; } = true;

    [JsonPropertyName("include_system_messages")]
    public bool IncludeSystemMessages { get; set; } = true;

    [JsonPropertyName("include_attachments")]
    public bool IncludeAttachments { get; set; } = true;
}

public sealed class JobRequestDocument
{
    [JsonPropertyName("schema_version")]
    public int SchemaVersion { get; set; } = 1;

    [JsonPropertyName("job_id")]
    public string JobId { get; set; } = "";

    [JsonPropertyName("created_at")]
    public string CreatedAt { get; set; } = "";

    [JsonPropertyName("output_root_id")]
    public string OutputRootId { get; set; } = "";

    [JsonPropertyName("output_root_path")]
    public string OutputRootPath { get; set; } = "";

    [JsonPropertyName("profile")]
    public string Profile { get; set; } = "timeline-default";

    [JsonPropertyName("reprocess_duplicates")]
    public bool ReprocessDuplicates { get; set; }

    [JsonPropertyName("parser_options")]
    public ParserOptionsDocument ParserOptions { get; set; } = new();

    [JsonPropertyName("input_items")]
    public List<InputItemDocument> InputItems { get; set; } = [];
}

public sealed class JobStatusDocument
{
    [JsonPropertyName("schema_version")]
    public int SchemaVersion { get; set; } = 1;

    [JsonPropertyName("job_id")]
    public string JobId { get; set; } = "";

    [JsonPropertyName("state")]
    public string State { get; set; } = "pending";

    [JsonPropertyName("current_stage")]
    public string CurrentStage { get; set; } = "queued";

    [JsonPropertyName("message")]
    public string Message { get; set; } = "";

    [JsonPropertyName("warnings")]
    public List<string> Warnings { get; set; } = [];

    [JsonPropertyName("conversations_total")]
    public int ConversationsTotal { get; set; }

    [JsonPropertyName("conversations_done")]
    public int ConversationsDone { get; set; }

    [JsonPropertyName("conversations_skipped")]
    public int ConversationsSkipped { get; set; }

    [JsonPropertyName("conversations_failed")]
    public int ConversationsFailed { get; set; }

    [JsonPropertyName("current_conversation")]
    public string? CurrentConversation { get; set; }

    [JsonPropertyName("estimated_remaining_sec")]
    public double? EstimatedRemainingSec { get; set; }

    [JsonPropertyName("progress_percent")]
    public double ProgressPercent { get; set; }

    [JsonPropertyName("started_at")]
    public string? StartedAt { get; set; }

    [JsonPropertyName("updated_at")]
    public string? UpdatedAt { get; set; }

    [JsonPropertyName("completed_at")]
    public string? CompletedAt { get; set; }
}

public sealed class JobResultDocument
{
    [JsonPropertyName("schema_version")]
    public int SchemaVersion { get; set; } = 1;

    [JsonPropertyName("job_id")]
    public string JobId { get; set; } = "";

    [JsonPropertyName("state")]
    public string State { get; set; } = "pending";

    [JsonPropertyName("run_dir")]
    public string RunDir { get; set; } = "";

    [JsonPropertyName("output_root_id")]
    public string OutputRootId { get; set; } = "";

    [JsonPropertyName("output_root_path")]
    public string OutputRootPath { get; set; } = "";

    [JsonPropertyName("processed_count")]
    public int ProcessedCount { get; set; }

    [JsonPropertyName("skipped_count")]
    public int SkippedCount { get; set; }

    [JsonPropertyName("error_count")]
    public int ErrorCount { get; set; }

    [JsonPropertyName("batch_count")]
    public int BatchCount { get; set; }

    [JsonPropertyName("conversation_index_path")]
    public string? ConversationIndexPath { get; set; }

    [JsonPropertyName("archive_path")]
    public string? ArchivePath { get; set; }

    [JsonPropertyName("warnings")]
    public List<string> Warnings { get; set; } = [];
}

public sealed class ManifestItemDocument
{
    [JsonPropertyName("conversation_id")]
    public string ConversationId { get; set; } = "";

    [JsonPropertyName("title")]
    public string Title { get; set; } = "";

    [JsonPropertyName("status")]
    public string Status { get; set; } = "pending";

    [JsonPropertyName("started_at_utc")]
    public string? StartedAtUtc { get; set; }

    [JsonPropertyName("ended_at_utc")]
    public string? EndedAtUtc { get; set; }

    [JsonPropertyName("message_count_total")]
    public int MessageCountTotal { get; set; }

    [JsonPropertyName("main_branch_message_count")]
    public int MainBranchMessageCount { get; set; }

    [JsonPropertyName("branch_count")]
    public int BranchCount { get; set; }

    [JsonPropertyName("attachment_count")]
    public int AttachmentCount { get; set; }

    [JsonPropertyName("image_count")]
    public int ImageCount { get; set; }

    [JsonPropertyName("audio_count")]
    public int AudioCount { get; set; }

    [JsonPropertyName("tool_count")]
    public int ToolCount { get; set; }

    [JsonPropertyName("has_tool_messages")]
    public bool HasToolMessages { get; set; }

    [JsonPropertyName("has_system_messages")]
    public bool HasSystemMessages { get; set; }

    [JsonPropertyName("has_attachments")]
    public bool HasAttachments { get; set; }

    [JsonPropertyName("has_multimodal_content")]
    public bool HasMultimodalContent { get; set; }

    [JsonPropertyName("timeline_path")]
    public string? TimelinePath { get; set; }
}

public sealed class ManifestDocument
{
    [JsonPropertyName("schema_version")]
    public int SchemaVersion { get; set; } = 1;

    [JsonPropertyName("job_id")]
    public string JobId { get; set; } = "";

    [JsonPropertyName("generated_at")]
    public string GeneratedAt { get; set; } = "";

    [JsonPropertyName("items")]
    public List<ManifestItemDocument> Items { get; set; } = [];
}

public sealed class ConversationSummaryDocument
{
    [JsonPropertyName("conversation_id")]
    public string ConversationId { get; set; } = "";

    [JsonPropertyName("title")]
    public string Title { get; set; } = "";

    [JsonPropertyName("create_time")]
    public string? CreateTime { get; set; }

    [JsonPropertyName("update_time")]
    public string? UpdateTime { get; set; }

    [JsonPropertyName("started_at_utc")]
    public string? StartedAtUtc { get; set; }

    [JsonPropertyName("ended_at_utc")]
    public string? EndedAtUtc { get; set; }

    [JsonPropertyName("default_model_slug")]
    public string? DefaultModelSlug { get; set; }

    [JsonPropertyName("message_count_total")]
    public int MessageCountTotal { get; set; }

    [JsonPropertyName("main_branch_message_count")]
    public int MainBranchMessageCount { get; set; }

    [JsonPropertyName("branch_count")]
    public int BranchCount { get; set; }

    [JsonPropertyName("attachment_count")]
    public int AttachmentCount { get; set; }

    [JsonPropertyName("image_count")]
    public int ImageCount { get; set; }

    [JsonPropertyName("audio_count")]
    public int AudioCount { get; set; }

    [JsonPropertyName("tool_count")]
    public int ToolCount { get; set; }

    [JsonPropertyName("has_tool_messages")]
    public bool HasToolMessages { get; set; }

    [JsonPropertyName("has_system_messages")]
    public bool HasSystemMessages { get; set; }

    [JsonPropertyName("has_attachments")]
    public bool HasAttachments { get; set; }

    [JsonPropertyName("has_multimodal_content")]
    public bool HasMultimodalContent { get; set; }

    [JsonPropertyName("role_counts_total")]
    public Dictionary<string, int> RoleCountsTotal { get; set; } = [];

    [JsonPropertyName("content_type_counts_total")]
    public Dictionary<string, int> ContentTypeCountsTotal { get; set; } = [];

    [JsonPropertyName("main_branch_role_counts")]
    public Dictionary<string, int> MainBranchRoleCounts { get; set; } = [];

    [JsonPropertyName("main_branch_content_type_counts")]
    public Dictionary<string, int> MainBranchContentTypeCounts { get; set; } = [];

    [JsonPropertyName("status")]
    public string Status { get; set; } = "pending";

    [JsonPropertyName("timeline_path")]
    public string? TimelinePath { get; set; }
}

public sealed class ExportSummaryDocument
{
    [JsonPropertyName("job_id")]
    public string JobId { get; set; } = "";

    [JsonPropertyName("input_name")]
    public string InputName { get; set; } = "";

    [JsonPropertyName("conversation_files")]
    public int ConversationFiles { get; set; }

    [JsonPropertyName("total_conversations")]
    public int TotalConversations { get; set; }

    [JsonPropertyName("total_messages")]
    public int TotalMessages { get; set; }

    [JsonPropertyName("message_role_counts")]
    public Dictionary<string, int> MessageRoleCounts { get; set; } = [];

    [JsonPropertyName("message_content_type_counts")]
    public Dictionary<string, int> MessageContentTypeCounts { get; set; } = [];

    [JsonPropertyName("date_min_utc")]
    public string? DateMinUtc { get; set; }

    [JsonPropertyName("date_max_utc")]
    public string? DateMaxUtc { get; set; }
}

public sealed class RunSummary
{
    public string JobId { get; set; } = "";
    public string RunDirectory { get; set; } = "";
    public string State { get; set; } = "pending";
    public string CurrentStage { get; set; } = "queued";
    public int ConversationsTotal { get; set; }
    public int ConversationsDone { get; set; }
    public int ConversationsSkipped { get; set; }
    public int ConversationsFailed { get; set; }
    public long TotalSizeBytes { get; set; }
    public double ProgressPercent { get; set; }
    public double? EstimatedRemainingSec { get; set; }
    public string? CreatedAt { get; set; }
    public bool HasDownloadableArchive { get; set; }
}

public sealed class RunDetails
{
    public string JobId { get; set; } = "";
    public string RunDirectory { get; set; } = "";
    public JobRequestDocument? Request { get; set; }
    public JobStatusDocument? Status { get; set; }
    public JobResultDocument? Result { get; set; }
    public ManifestDocument? Manifest { get; set; }
    public ExportSummaryDocument? ExportSummary { get; set; }
    public IReadOnlyList<ConversationSummaryDocument> Conversations { get; set; } = [];
    public string LogTail { get; set; } = "";
}

public sealed class ConversationDetails
{
    public string JobId { get; set; } = "";
    public string ConversationId { get; set; } = "";
    public string Title { get; set; } = "";
    public string? CreateTime { get; set; }
    public string? UpdateTime { get; set; }
    public string? StartedAtUtc { get; set; }
    public string? EndedAtUtc { get; set; }
    public string? DefaultModelSlug { get; set; }
    public int MessageCountTotal { get; set; }
    public int MainBranchMessageCount { get; set; }
    public int BranchCount { get; set; }
    public int AttachmentCount { get; set; }
    public int ImageCount { get; set; }
    public int AudioCount { get; set; }
    public int ToolCount { get; set; }
    public bool HasToolMessages { get; set; }
    public bool HasSystemMessages { get; set; }
    public bool HasAttachments { get; set; }
    public bool HasMultimodalContent { get; set; }
    public IReadOnlyDictionary<string, int> RoleCountsTotal { get; set; } = new Dictionary<string, int>();
    public IReadOnlyDictionary<string, int> ContentTypeCountsTotal { get; set; } = new Dictionary<string, int>();
    public IReadOnlyDictionary<string, int> MainBranchRoleCounts { get; set; } = new Dictionary<string, int>();
    public IReadOnlyDictionary<string, int> MainBranchContentTypeCounts { get; set; } = new Dictionary<string, int>();
    public string TimelineMarkdown { get; set; } = "";
    public string TimelinePath { get; set; } = "";
    public string ConversationJsonPath { get; set; } = "";
}
