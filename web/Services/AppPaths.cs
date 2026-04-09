namespace TimelineForChatGPT.Web.Services;

public sealed class AppPaths(IConfiguration configuration)
{
    public string RuntimeDefaultsPath { get; } =
        configuration["TIMELINE_FOR_CHATGPT_RUNTIME_DEFAULTS"] ?? "/app/config/runtime.defaults.json";

    public string AppDataRoot { get; } =
        configuration["TIMELINE_FOR_CHATGPT_APPDATA_ROOT"] ?? "/shared/app-data";

    public string UploadsRoot { get; } =
        configuration["TIMELINE_FOR_CHATGPT_UPLOADS_ROOT"] ?? "/shared/uploads";

    public string OutputsRoot { get; } =
        configuration["TIMELINE_FOR_CHATGPT_OUTPUTS_ROOT"] ?? "/shared/outputs";

    public string SettingsPath => Path.Combine(AppDataRoot, "settings.json");
}
