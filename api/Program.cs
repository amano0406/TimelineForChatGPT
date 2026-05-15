using System.Globalization;
using System.Text.Json;

var settingsPath = Environment.GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_SETTINGS")
    ?? Path.Combine(Directory.GetCurrentDirectory(), "settings.json");

var listenPort = ResolveListenPort(settingsPath);
var builder = WebApplication.CreateBuilder(args);
builder.WebHost.UseUrls($"http://0.0.0.0:{listenPort}");

var app = builder.Build();

app.MapGet("/health", () => Results.Json(IsHealthy(settingsPath)));

app.Run();

static int ResolveListenPort(string settingsPath)
{
    var configured = Environment.GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_API_LISTEN_PORT")
        ?? Environment.GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_API_PORT")
        ?? ReadApiPort(settingsPath);

    return int.TryParse(configured, NumberStyles.Integer, CultureInfo.InvariantCulture, out var port)
        && port is >= 1 and <= 65535
        ? port
        : 19300;
}

static string? ReadApiPort(string settingsPath)
{
    try
    {
        using var document = JsonDocument.Parse(File.ReadAllText(settingsPath));
        if (document.RootElement.TryGetProperty("runtime", out var runtime)
            && runtime.ValueKind == JsonValueKind.Object
            && runtime.TryGetProperty("apiPort", out var apiPort))
        {
            return apiPort.ValueKind == JsonValueKind.Number
                ? apiPort.GetInt32().ToString(CultureInfo.InvariantCulture)
                : apiPort.GetString();
        }
    }
    catch
    {
        return null;
    }

    return null;
}

static bool IsHealthy(string settingsPath)
{
    try
    {
        if (!File.Exists(settingsPath))
        {
            return false;
        }

        using var document = JsonDocument.Parse(File.ReadAllText(settingsPath));
        if (document.RootElement.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        if (!document.RootElement.TryGetProperty("outputRoot", out var outputRoot)
            || outputRoot.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(outputRoot.GetString()))
        {
            return false;
        }

        if (document.RootElement.TryGetProperty("runtime", out var runtime)
            && runtime.ValueKind == JsonValueKind.Object
            && runtime.TryGetProperty("apiPort", out var apiPort)
            && !IsValidPort(apiPort))
        {
            return false;
        }

        return true;
    }
    catch
    {
        return false;
    }
}

static bool IsValidPort(JsonElement apiPort)
{
    if (apiPort.ValueKind == JsonValueKind.Number && apiPort.TryGetInt32(out var numericPort))
    {
        return numericPort is >= 1 and <= 65535;
    }

    if (apiPort.ValueKind == JsonValueKind.String
        && int.TryParse(apiPort.GetString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var textPort))
    {
        return textPort is >= 1 and <= 65535;
    }

    return false;
}
