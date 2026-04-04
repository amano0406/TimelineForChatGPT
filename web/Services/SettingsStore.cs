using System.Text.Json;
using ChatGpt2Timeline.Web.Models;

namespace ChatGpt2Timeline.Web.Services;

public sealed class SettingsStore(AppPaths paths)
{
    private readonly JsonSerializerOptions _jsonOptions = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true,
    };

    public async Task<AppSettingsDocument> LoadAsync(CancellationToken cancellationToken = default)
    {
        if (File.Exists(paths.SettingsPath))
        {
            await using var stream = File.OpenRead(paths.SettingsPath);
            var loaded = await JsonSerializer.DeserializeAsync<AppSettingsDocument>(
                stream,
                _jsonOptions,
                cancellationToken);
            return Normalize(loaded ?? new AppSettingsDocument());
        }

        if (File.Exists(paths.RuntimeDefaultsPath))
        {
            await using var stream = File.OpenRead(paths.RuntimeDefaultsPath);
            var defaults = await JsonSerializer.DeserializeAsync<AppSettingsDocument>(
                stream,
                _jsonOptions,
                cancellationToken);
            return Normalize(defaults ?? new AppSettingsDocument());
        }

        return Normalize(new AppSettingsDocument());
    }

    private AppSettingsDocument Normalize(AppSettingsDocument settings)
    {
        settings.InputRoots =
        [
            new RootOption
            {
                Id = "uploads",
                DisplayName = "Uploads",
                Path = paths.UploadsRoot,
                Enabled = true,
            },
        ];

        settings.OutputRoots =
        [
            new RootOption
            {
                Id = "runs",
                DisplayName = "Runs",
                Path = paths.OutputsRoot,
                Enabled = true,
            },
        ];

        settings.AllowedExtensions = [".zip"];
        return settings;
    }
}
