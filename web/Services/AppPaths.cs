namespace ChatGpt2Timeline.Web.Services;

public sealed class AppPaths(IConfiguration configuration)
{
    public string RuntimeDefaultsPath { get; } =
        configuration["CHATGPT2TIMELINE_RUNTIME_DEFAULTS"] ?? "/app/config/runtime.defaults.json";

    public string AppDataRoot { get; } =
        configuration["CHATGPT2TIMELINE_APPDATA_ROOT"] ?? "/shared/app-data";

    public string UploadsRoot { get; } =
        configuration["CHATGPT2TIMELINE_UPLOADS_ROOT"] ?? "/shared/uploads";

    public string OutputsRoot { get; } =
        configuration["CHATGPT2TIMELINE_OUTPUTS_ROOT"] ?? "/shared/outputs";

    public string SettingsPath => Path.Combine(AppDataRoot, "settings.json");
}
