using System.Globalization;
using Microsoft.AspNetCore.Localization;

namespace ChatGpt2Timeline.Web.Localization;

public sealed class UiText(IHttpContextAccessor httpContextAccessor)
{
    private static readonly IReadOnlyDictionary<string, string> English = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["Nav.Jobs"] = "Jobs",
        ["Nav.NewJob"] = "New Job",
        ["Language.Japanese"] = "日本語",
        ["Language.English"] = "English",
        ["Page.Jobs.Title"] = "Jobs",
        ["Page.Jobs.Description"] = "Manage ChatGPT export jobs in a flow close to `video2timeline`.",
        ["Page.Jobs.ActiveJob"] = "Active Job",
        ["Page.Jobs.Open"] = "Open",
        ["Page.Jobs.Progress"] = "Progress",
        ["Page.Jobs.InputSize"] = "Input Size",
        ["Page.Jobs.Remaining"] = "Remaining",
        ["Page.Jobs.Created"] = "Created",
        ["Page.Jobs.RecentJobs"] = "Recent Jobs",
        ["Page.Jobs.Job"] = "Job",
        ["Page.Jobs.State"] = "State",
        ["Page.Jobs.NoJobs"] = "No jobs yet.",
        ["Page.Jobs.Details"] = "Details",
        ["Page.Jobs.DownloadZipShort"] = "ZIP",
        ["Page.NewJob.Title"] = "New Job",
        ["Page.NewJob.Description"] = "Upload one ChatGPT export ZIP and create a `video2timeline`-style job.",
        ["Page.NewJob.ScaffoldScope"] = "Scaffold Scope",
        ["Page.NewJob.ScaffoldDescription"] = "This scaffold currently treats ZIP upload as the primary input. The worker extracts the export and generates `export_summary.json`, `conversation_index.jsonl`, and a minimal `timeline.md`.",
        ["Page.NewJob.ExportZipLabel"] = "ChatGPT Export ZIP",
        ["Page.NewJob.ReprocessDuplicates"] = "Reprocess even when the export appears to be a duplicate",
        ["Page.NewJob.CreateJob"] = "Create Job",
        ["Page.NewJob.Cancel"] = "Cancel",
        ["Page.Details.Title"] = "Job Details",
        ["Page.Details.DownloadZip"] = "Download ZIP",
        ["Page.Details.CurrentConversation"] = "Current Conversation",
        ["Page.Details.Updated"] = "Updated",
        ["Page.Details.Result"] = "Result",
        ["Page.Details.Processed"] = "Processed",
        ["Page.Details.Failed"] = "Failed",
        ["Page.Details.BatchCount"] = "Batch Count",
        ["Page.Details.IndexPath"] = "Index Path",
        ["Page.Details.ExportSummary"] = "Export Summary",
        ["Page.Details.Input"] = "Input",
        ["Page.Details.ConversationFiles"] = "Conversation Files",
        ["Page.Details.Conversations"] = "Conversations",
        ["Page.Details.Messages"] = "Messages",
        ["Page.Details.DateRange"] = "Date Range",
        ["Page.Details.WorkerLog"] = "Worker Log",
        ["Page.Details.NoLogYet"] = "No log yet.",
        ["Page.Details.TableTitle"] = "Title",
        ["Page.Details.TableBranches"] = "Branches",
        ["Page.Details.TableAssets"] = "Assets",
        ["Page.Details.TableUpdated"] = "Updated",
        ["Page.Details.ConversationIndexPending"] = "Conversation index not generated yet.",
        ["Page.Details.Timeline"] = "Timeline",
        ["Page.Conversation.Title"] = "Conversation",
        ["Page.Conversation.Back"] = "Back",
        ["Page.Conversation.Metadata"] = "Metadata",
        ["Page.Conversation.Created"] = "Created",
        ["Page.Conversation.Started"] = "Started",
        ["Page.Conversation.Ended"] = "Ended",
        ["Page.Conversation.Model"] = "Model",
        ["Page.Conversation.Assets"] = "Assets",
        ["Page.Conversation.ToolMessages"] = "Tool Messages",
        ["Page.Conversation.Flags"] = "Flags",
        ["Page.Conversation.RoleCounts"] = "Role Counts",
        ["Page.Conversation.ContentTypes"] = "Content Types",
        ["Page.Conversation.MainBranchRoles"] = "Main Branch Roles",
        ["Page.Conversation.MainBranchTypes"] = "Main Branch Types",
        ["Page.Conversation.TimelinePath"] = "Timeline Path",
        ["Page.Conversation.ConversationJson"] = "Conversation JSON",
        ["Page.Conversation.TimelineMarkdown"] = "Timeline Markdown",
        ["Page.Error.Title"] = "Error",
        ["Page.Error.Header"] = "Error.",
        ["Page.Error.Description"] = "An error occurred while processing your request.",
        ["Page.Error.RequestId"] = "Request ID:",
        ["Page.Error.DevelopmentMode"] = "Development Mode",
        ["Page.Error.DevelopmentDescription"] = "Swapping to the Development environment displays detailed information about the error that occurred.",
        ["Page.Error.DevelopmentWarning"] = "The Development environment shouldn't be enabled for deployed applications.",
        ["Page.Error.DevelopmentWarningBody"] = "It can result in displaying sensitive information from exceptions to end users. For local debugging, enable the Development environment by setting the ASPNETCORE_ENVIRONMENT environment variable to Development and restarting the app.",
        ["Page.Index.Title"] = "Redirecting",
        ["Page.Privacy.Title"] = "Privacy Policy",
        ["Page.Privacy.Body"] = "Use this page to detail your site's privacy policy.",
        ["Unit.Seconds"] = "sec",
        ["Asset.Attachments"] = "attachments",
        ["Asset.Images"] = "images",
        ["Asset.Audio"] = "audio",
        ["Asset.ImageShort"] = "img",
        ["Asset.AudioShort"] = "audio",
        ["Flag.tool"] = "tool",
        ["Flag.system"] = "system",
        ["Flag.assets"] = "assets",
        ["Flag.multimodal"] = "multimodal",
        ["State.pending"] = "Pending",
        ["State.running"] = "Running",
        ["State.completed"] = "Completed",
        ["State.failed"] = "Failed",
        ["Stage.queued"] = "Queued",
        ["Stage.starting"] = "Starting",
        ["Stage.extract_zip"] = "Extract ZIP",
        ["Stage.parse_conversations"] = "Parse Conversations",
        ["Stage.build_indexes"] = "Build Indexes",
        ["Stage.completed"] = "Completed",
        ["Stage.failed"] = "Failed",
        ["Validation.SelectExportZip"] = "Select one ChatGPT export ZIP.",
        ["Validation.UploadEmpty"] = "The upload file is empty.",
        ["Validation.OnlyZipSupported"] = "Only ChatGPT export ZIP files are supported in this scaffold.",
        ["Validation.NoOutputRoot"] = "No output root is configured.",
        ["Validation.TimelinePending"] = "Timeline has not been rendered yet.",
        ["Validation.ZipEmpty"] = "The ZIP archive is empty.",
        ["Validation.ZipUnreadable"] = "The uploaded ZIP could not be opened. Older ChatGPT export downloads can be corrupted, so please use a freshly downloaded ZIP."
    };

    private static readonly IReadOnlyDictionary<string, string> Japanese = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["Nav.Jobs"] = "ジョブ",
        ["Nav.NewJob"] = "新規ジョブ",
        ["Language.Japanese"] = "日本語",
        ["Language.English"] = "English",
        ["Page.Jobs.Title"] = "ジョブ",
        ["Page.Jobs.Description"] = "`video2timeline` に近いフローで ChatGPT export ジョブを管理します。",
        ["Page.Jobs.ActiveJob"] = "実行中ジョブ",
        ["Page.Jobs.Open"] = "開く",
        ["Page.Jobs.Progress"] = "進捗",
        ["Page.Jobs.InputSize"] = "入力サイズ",
        ["Page.Jobs.Remaining"] = "残り",
        ["Page.Jobs.Created"] = "作成日時",
        ["Page.Jobs.RecentJobs"] = "最近のジョブ",
        ["Page.Jobs.Job"] = "ジョブ",
        ["Page.Jobs.State"] = "状態",
        ["Page.Jobs.NoJobs"] = "まだジョブはありません。",
        ["Page.Jobs.Details"] = "詳細",
        ["Page.Jobs.DownloadZipShort"] = "ZIP",
        ["Page.NewJob.Title"] = "新規ジョブ",
        ["Page.NewJob.Description"] = "ChatGPT export ZIP を 1 件投入して、`video2timeline` 型のジョブを作成します。",
        ["Page.NewJob.ScaffoldScope"] = "スキャフォールド範囲",
        ["Page.NewJob.ScaffoldDescription"] = "現在は ZIP アップロードを主入力にしています。worker は export を展開し、`export_summary.json` と `conversation_index.jsonl`、最小の `timeline.md` を生成します。",
        ["Page.NewJob.ExportZipLabel"] = "ChatGPT エクスポート ZIP",
        ["Page.NewJob.ReprocessDuplicates"] = "同名 export の再投入でも再処理する",
        ["Page.NewJob.CreateJob"] = "ジョブを作成",
        ["Page.NewJob.Cancel"] = "キャンセル",
        ["Page.Details.Title"] = "ジョブ詳細",
        ["Page.Details.DownloadZip"] = "ZIP をダウンロード",
        ["Page.Details.CurrentConversation"] = "現在の会話",
        ["Page.Details.Updated"] = "更新日時",
        ["Page.Details.Result"] = "結果",
        ["Page.Details.Processed"] = "処理済み",
        ["Page.Details.Failed"] = "失敗",
        ["Page.Details.BatchCount"] = "バッチ数",
        ["Page.Details.IndexPath"] = "インデックスパス",
        ["Page.Details.ExportSummary"] = "エクスポート概要",
        ["Page.Details.Input"] = "入力",
        ["Page.Details.ConversationFiles"] = "会話ファイル数",
        ["Page.Details.Conversations"] = "会話数",
        ["Page.Details.Messages"] = "メッセージ数",
        ["Page.Details.DateRange"] = "日付範囲",
        ["Page.Details.WorkerLog"] = "ワーカーログ",
        ["Page.Details.NoLogYet"] = "まだログはありません。",
        ["Page.Details.TableTitle"] = "タイトル",
        ["Page.Details.TableBranches"] = "分岐",
        ["Page.Details.TableAssets"] = "アセット",
        ["Page.Details.TableUpdated"] = "更新",
        ["Page.Details.ConversationIndexPending"] = "会話インデックスはまだ生成されていません。",
        ["Page.Details.Timeline"] = "タイムライン",
        ["Page.Conversation.Title"] = "会話",
        ["Page.Conversation.Back"] = "戻る",
        ["Page.Conversation.Metadata"] = "メタデータ",
        ["Page.Conversation.Created"] = "作成",
        ["Page.Conversation.Started"] = "開始",
        ["Page.Conversation.Ended"] = "終了",
        ["Page.Conversation.Model"] = "モデル",
        ["Page.Conversation.Assets"] = "アセット",
        ["Page.Conversation.ToolMessages"] = "ツールメッセージ数",
        ["Page.Conversation.Flags"] = "フラグ",
        ["Page.Conversation.RoleCounts"] = "ロール件数",
        ["Page.Conversation.ContentTypes"] = "コンテンツタイプ件数",
        ["Page.Conversation.MainBranchRoles"] = "主系統ロール件数",
        ["Page.Conversation.MainBranchTypes"] = "主系統コンテンツタイプ件数",
        ["Page.Conversation.TimelinePath"] = "タイムラインパス",
        ["Page.Conversation.ConversationJson"] = "会話 JSON",
        ["Page.Conversation.TimelineMarkdown"] = "タイムライン Markdown",
        ["Page.Error.Title"] = "エラー",
        ["Page.Error.Header"] = "エラー",
        ["Page.Error.Description"] = "リクエストの処理中にエラーが発生しました。",
        ["Page.Error.RequestId"] = "リクエスト ID:",
        ["Page.Error.DevelopmentMode"] = "開発モード",
        ["Page.Error.DevelopmentDescription"] = "Development 環境では、発生したエラーの詳細情報が表示されます。",
        ["Page.Error.DevelopmentWarning"] = "デプロイ済みアプリでは Development 環境を有効にしないでください。",
        ["Page.Error.DevelopmentWarningBody"] = "エンドユーザーに例外の機微情報が表示されるおそれがあります。ローカルデバッグでは ASPNETCORE_ENVIRONMENT を Development に設定して再起動してください。",
        ["Page.Index.Title"] = "リダイレクト中",
        ["Page.Privacy.Title"] = "プライバシーポリシー",
        ["Page.Privacy.Body"] = "このページにサイトのプライバシーポリシーを記載します。",
        ["Unit.Seconds"] = "秒",
        ["Asset.Attachments"] = "添付",
        ["Asset.Images"] = "画像",
        ["Asset.Audio"] = "音声",
        ["Asset.ImageShort"] = "画像",
        ["Asset.AudioShort"] = "音声",
        ["Flag.tool"] = "ツール",
        ["Flag.system"] = "システム",
        ["Flag.assets"] = "アセット",
        ["Flag.multimodal"] = "マルチモーダル",
        ["State.pending"] = "待機中",
        ["State.running"] = "実行中",
        ["State.completed"] = "完了",
        ["State.failed"] = "失敗",
        ["Stage.queued"] = "キュー待ち",
        ["Stage.starting"] = "開始中",
        ["Stage.extract_zip"] = "ZIP 展開",
        ["Stage.parse_conversations"] = "会話解析",
        ["Stage.build_indexes"] = "インデックス生成",
        ["Stage.completed"] = "完了",
        ["Stage.failed"] = "失敗",
        ["Validation.SelectExportZip"] = "ChatGPT export ZIP を 1 件選択してください。",
        ["Validation.UploadEmpty"] = "アップロードファイルが空です。",
        ["Validation.OnlyZipSupported"] = "このスキャフォールドでは ChatGPT export ZIP のみを受け付けます。",
        ["Validation.NoOutputRoot"] = "出力先ルートが設定されていません。",
        ["Validation.TimelinePending"] = "タイムラインはまだ生成されていません。",
        ["Validation.ZipEmpty"] = "ZIP アーカイブが空です。",
        ["Validation.ZipUnreadable"] = "アップロードされた ZIP を開けませんでした。ChatGPT export の古いダウンロードには壊れたものがあるので、再ダウンロードした ZIP を使ってください。"
    };

    public CultureInfo CurrentCulture =>
        httpContextAccessor.HttpContext?.Features.Get<IRequestCultureFeature>()?.RequestCulture.UICulture
        ?? CultureInfo.CurrentUICulture;

    public string CurrentLanguage => CurrentCulture.TwoLetterISOLanguageName;

    public string this[string key] => Get(key);

    public string this[string key, params object[] arguments] =>
        string.Format(CurrentCulture, Get(key), arguments);

    public string TranslateState(string? value) => TranslateWithPrefix("State", value);

    public string TranslateStage(string? value) => TranslateWithPrefix("Stage", value);

    public string TranslateFlag(string value) => Get($"Flag.{value}");

    private string TranslateWithPrefix(string prefix, string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return "-";
        }

        var key = $"{prefix}.{value}";
        return TryGet(key, out var translated) ? translated : value;
    }

    private string Get(string key) => TryGet(key, out var value) ? value : key;

    private bool TryGet(string key, out string value)
    {
        var language = CurrentLanguage.StartsWith("ja", StringComparison.OrdinalIgnoreCase)
            ? Japanese
            : English;

        if (language.TryGetValue(key, out value!))
        {
            return true;
        }

        return English.TryGetValue(key, out value!);
    }
}
