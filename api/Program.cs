using System.Diagnostics;
using System.Globalization;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

var paths = ProductPaths.Resolve(args);
var bindPort = ProductPaths.ReadPort(args, paths.SettingsPath, 19300);

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddSingleton(paths);
builder.Services.AddSingleton<ProductCommandRunner>();
if (string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("ASPNETCORE_URLS")))
{
    builder.WebHost.UseUrls($"http://127.0.0.1:{bindPort}");
}

var app = builder.Build();

app.MapGet("/health", () => Results.Json(IsHealthy(paths)));

var items = app.MapGroup("/items");

items.MapPost("/refresh", async (
    HttpContext context,
    ProductCommandRunner runner,
    CancellationToken cancellationToken) =>
{
    return await ExecuteJsonEndpointAsync(async () =>
    {
        var request = await ReadJsonObjectAsync(context, cancellationToken);
        return await runner.RunJsonAsync(
            BuildItemsRefreshArguments(request),
            TimeSpan.FromSeconds(1800),
            cancellationToken);
    });
});

items.MapPost("/list", async (
    HttpContext context,
    ProductPaths paths,
    CancellationToken cancellationToken) =>
{
    return await ExecuteJsonEndpointAsync(async () =>
    {
        var request = await ReadJsonObjectAsync(context, cancellationToken);
        return await BuildItemsListResponseAsync(paths, request, cancellationToken);
    });
});

items.MapPost("/detail", async (
    HttpContext context,
    ProductPaths paths,
    CancellationToken cancellationToken) =>
{
    return await ExecuteJsonEndpointAsync(async () =>
    {
        var request = await ReadJsonObjectAsync(context, cancellationToken);
        return await BuildItemsDetailResponseAsync(
            paths,
            request,
            ["conversation_id", "thread_id", "item_id", "id"],
            cancellationToken);
    });
});

items.MapPost("/download", async (
    HttpContext context,
    ProductPaths paths,
    CancellationToken cancellationToken) =>
{
    return await ExecuteJsonEndpointAsync(async () =>
    {
        var request = await ReadJsonObjectAsync(context, cancellationToken);
        return await BuildItemsDownloadResponseAsync(paths, request, cancellationToken);
    });
});

var settings = app.MapGroup("/settings");

settings.MapPost("/status", async (
    HttpContext context,
    ProductPaths paths,
    CancellationToken cancellationToken) =>
{
    return await ExecuteJsonEndpointAsync(async () =>
    {
        _ = await ReadJsonObjectAsync(context, cancellationToken);
        return await BuildSettingsStatusResponseAsync(paths, cancellationToken);
    });
});

settings.MapPost("/init", async (
    HttpContext context,
    ProductPaths paths,
    CancellationToken cancellationToken) =>
{
    return await ExecuteJsonEndpointAsync(async () =>
    {
        var request = await ReadJsonObjectAsync(context, cancellationToken);
        var force = GetBoolAny(request, ["force"], false);
        if (File.Exists(paths.SettingsPath) && !force)
        {
            return new JsonObject
            {
                ["ok"] = true,
                ["settingsPath"] = paths.SettingsPath,
                ["created"] = false,
            };
        }

        var settingsDirectory = Path.GetDirectoryName(paths.SettingsPath);
        if (!string.IsNullOrEmpty(settingsDirectory))
        {
            Directory.CreateDirectory(settingsDirectory);
        }

        var examplePath = Path.Combine(paths.ProductRoot, "settings.example.json");
        if (File.Exists(examplePath))
        {
            File.Copy(examplePath, paths.SettingsPath, overwrite: true);
        }
        else
        {
            await File.WriteAllTextAsync(
                paths.SettingsPath,
                """
                {
                  "schemaVersion": 1,
                  "runtime": {
                    "instanceName": "",
                    "apiPort": 19300
                  },
                  "outputRoot": "C:\\TimelineData\\chatgpt"
                }
                """,
                cancellationToken);
        }

        return new JsonObject
        {
            ["ok"] = true,
            ["settingsPath"] = paths.SettingsPath,
            ["created"] = true,
        };
    });
});

app.Run();

static bool IsHealthy(ProductPaths paths)
{
    if (!File.Exists(paths.DockerComposePath) || !File.Exists(paths.SettingsPath))
    {
        return false;
    }

    try
    {
        using var document = JsonDocument.Parse(File.ReadAllText(paths.SettingsPath));
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
            && !ProductPaths.IsValidPort(apiPort))
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

static async Task<IResult> ExecuteJsonEndpointAsync(Func<Task<JsonNode?>> operation)
{
    try
    {
        return Results.Json(await operation());
    }
    catch (ProductCommandException ex)
    {
        return Results.Json(
            ex.Payload ?? ErrorPayload(ex.Message),
            statusCode: StatusCodes.Status500InternalServerError);
    }
    catch (Exception ex) when (ex is not OperationCanceledException)
    {
        return Results.Json(
            ErrorPayload(ex.Message),
            statusCode: StatusCodes.Status500InternalServerError);
    }
}

static async Task<JsonObject?> ReadJsonObjectAsync(HttpContext context, CancellationToken cancellationToken)
{
    if (context.Request.ContentLength == 0)
    {
        return null;
    }

    try
    {
        return await context.Request.ReadFromJsonAsync<JsonObject>(cancellationToken: cancellationToken);
    }
    catch (JsonException ex)
    {
        throw new InvalidOperationException($"Invalid JSON request body: {ex.Message}", ex);
    }
}

static IReadOnlyList<string> BuildItemsRefreshArguments(JsonObject? request)
{
    var filePath = GetStringAny(request, ["filePath", "file", "inputPath", "input"]);
    if (string.IsNullOrWhiteSpace(filePath))
    {
        throw new InvalidOperationException("ChatGPT export ZIP is required.");
    }

    var arguments = new List<string>
    {
        "items",
        "refresh",
        "--file",
        filePath,
        "--json",
    };

    AddOptionalValue(arguments, "--download-to", GetStringAny(request, ["downloadTo", "download_to", "to"]));
    if (GetBoolAny(request, ["overwrite"], false))
    {
        arguments.Add("--overwrite");
    }

    return arguments;
}

static async Task<JsonObject> BuildItemsListResponseAsync(
    ProductPaths paths,
    JsonObject? request,
    CancellationToken cancellationToken)
{
    var outputRoot = await ResolveOutputRootAsync(paths, cancellationToken);
    var manifestPath = Path.Combine(outputRoot, "manifest.json");
    var manifest = await ReadJsonFileAsync(manifestPath, cancellationToken) ?? new JsonObject
    {
        ["schema_version"] = 1,
        ["application"] = "TimelineForChatGPT",
        ["item_count"] = 0,
        ["items"] = new JsonArray(),
    };

    var items = GetArray(manifest, "items")
        .OfType<JsonObject>()
        .OrderByDescending(ItemLatestTimestamp)
        .ThenByDescending(item => GetStringAny(item, ["conversation_id", "id"]))
        .ToList();
    var totalItems = items.Count;
    var itemCount = GetIntAny(manifest, ["item_count", "itemCount"]) ?? totalItems;
    var page = GetIntAny(request, ["page"]);
    var pageSize = GetIntAny(request, ["pageSize", "page_size"]);
    var pagingRequested = page is not null || pageSize is not null;
    var pageItems = pagingRequested
        ? items.Skip(((page ?? 1) - 1) * (pageSize ?? 100)).Take(pageSize ?? 100).ToList()
        : items;
    var pagination = pagingRequested
        ? BuildPagePagination(page ?? 1, pageSize ?? 100, totalItems, pageItems.Count)
        : BuildAllPagination(totalItems, pageItems.Count);

    var itemArray = new JsonArray();
    foreach (var item in pageItems)
    {
        itemArray.Add(item.DeepClone());
    }

    return new JsonObject
    {
        ["schema_version"] = 1,
        ["settings_path"] = paths.SettingsPath,
        ["output_root"] = outputRoot,
        ["item_count"] = itemCount,
        ["total_items"] = totalItems,
        ["pagination"] = pagination,
        ["sort"] = new JsonObject
        {
            ["order"] = "desc",
            ["fields"] = new JsonArray("updated_at", "ended_at_utc", "created_at", "started_at_utc", "conversation_id"),
        },
        ["items"] = itemArray,
        ["summary"] = pagingRequested
            ? $"{itemCount} conversations in output; showing {GetIntAny(pagination, ["range_start"]) ?? 0}-{GetIntAny(pagination, ["range_end"]) ?? 0} of {totalItems} latest-first"
            : $"{itemCount} conversations in output; showing all {pageItems.Count} latest-first",
    };
}

static async Task<JsonObject> BuildItemsDownloadResponseAsync(
    ProductPaths paths,
    JsonObject? request,
    CancellationToken cancellationToken)
{
    var outputRoot = await ResolveOutputRootAsync(paths, cancellationToken);
    var manifestPath = Path.Combine(outputRoot, "manifest.json");
    var manifest = await ReadJsonFileAsync(manifestPath, cancellationToken)
        ?? throw new FileNotFoundException($"No output manifest exists: {manifestPath}");
    var destinationText = GetStringAny(request, ["to", "downloadTo", "download_to", "outputPath", "output_path"]);
    if (string.IsNullOrWhiteSpace(destinationText))
    {
        throw new InvalidOperationException("Download destination is required.");
    }

    var overwrite = GetBoolAny(request, ["overwrite"], false);
    var destinationPath = ResolveDownloadDestination(destinationText, manifest);
    if (File.Exists(destinationPath))
    {
        if (!overwrite)
        {
            throw new IOException($"Download target already exists: {destinationPath}");
        }
        File.Delete(destinationPath);
    }

    var parent = Path.GetDirectoryName(destinationPath);
    if (!string.IsNullOrWhiteSpace(parent))
    {
        Directory.CreateDirectory(parent);
    }

    using (var archive = ZipFile.Open(destinationPath, ZipArchiveMode.Create))
    {
        AddTextEntry(archive, "README.md", BuildChatGptDownloadReadme(manifest));
        foreach (var item in GetArray(manifest, "items").OfType<JsonObject>())
        {
            var conversationId = GetStringAny(item, ["conversation_id", "id"]);
            if (string.IsNullOrWhiteSpace(conversationId))
            {
                continue;
            }

            var itemRoot = GetSafeChildDirectory(outputRoot, conversationId);
            archive.CreateEntryFromFile(
                Path.Combine(itemRoot, "convert_info.json"),
                $"items/{conversationId}/convert_info.json");
            archive.CreateEntryFromFile(
                Path.Combine(itemRoot, "timeline.json"),
                $"items/{conversationId}/timeline.json");
        }
    }

    return new JsonObject
    {
        ["schema_version"] = 1,
        ["source_output_root"] = outputRoot,
        ["download_path"] = destinationPath,
    };
}

static async Task<JsonObject> BuildSettingsStatusResponseAsync(
    ProductPaths paths,
    CancellationToken cancellationToken)
{
    var settings = await ReadJsonFileAsync(paths.SettingsPath, cancellationToken);
    var outputRoot = await ResolveOutputRootAsync(paths, cancellationToken);
    var settingsDirectory = Path.GetDirectoryName(paths.SettingsPath) ?? paths.ProductRoot;
    var runtime = GetNode(settings, "runtime") as JsonObject;
    var apiPort = GetIntAny(runtime, ["apiPort"]) ?? 19300;
    var instanceName = GetStringAny(runtime, ["instanceName"]);
    var runRoot = ResolveInternalRuntimePath(
        "TIMELINE_FOR_CHATGPT_OUTPUTS_ROOT",
        Path.Combine(settingsDirectory, ".app-data", "runs"),
        settingsDirectory);
    var stateRoot = ResolveInternalRuntimePath(
        "TIMELINE_FOR_CHATGPT_STATE_ROOT",
        Path.Combine(settingsDirectory, ".app-data", "state"),
        settingsDirectory);
    var cacheRoot = ResolveInternalRuntimePath(
        "TIMELINE_FOR_CHATGPT_CACHE_ROOT",
        Path.Combine(settingsDirectory, ".app-data", "cache"),
        settingsDirectory);

    return new JsonObject
    {
        ["schema_version"] = 1,
        ["settings_path"] = paths.SettingsPath,
        ["settings_exists"] = File.Exists(paths.SettingsPath),
        ["output_root"] = outputRoot,
        ["outputRoot"] = outputRoot,
        ["run_root"] = runRoot,
        ["state_root"] = stateRoot,
        ["cache_root"] = cacheRoot,
        ["runtime"] = new JsonObject
        {
            ["instance_name"] = instanceName,
            ["api_port"] = apiPort,
            ["instanceName"] = instanceName,
            ["apiPort"] = apiPort,
        },
        ["warnings"] = new JsonArray(),
        ["summary"] = $"output={outputRoot} runs={runRoot} state={stateRoot} cache={cacheRoot} api={apiPort}",
    };
}

static async Task<JsonObject> BuildItemsDetailResponseAsync(
    ProductPaths paths,
    JsonObject? request,
    string[] itemIdNames,
    CancellationToken cancellationToken)
{
    var requestedItemId = GetStringAny(
        request,
        ["itemId", "item_id", "threadId", "thread_id", "conversationId", "conversation_id", "id"]);
    if (string.IsNullOrWhiteSpace(requestedItemId))
    {
        return NewUnavailableThreadDetail(
            string.Empty,
            string.Empty,
            string.Empty,
            string.Empty,
            "Item id is required.");
    }

    var outputRoot = await ResolveOutputRootAsync(paths, cancellationToken);
    if (string.IsNullOrWhiteSpace(outputRoot) || !Directory.Exists(outputRoot))
    {
        return NewUnavailableThreadDetail(
            requestedItemId,
            outputRoot,
            string.Empty,
            string.Empty,
            "Output directory is not configured.");
    }

    string itemDirectory;
    try
    {
        itemDirectory = GetSafeChildDirectory(outputRoot, requestedItemId);
    }
    catch (InvalidOperationException ex)
    {
        return NewUnavailableThreadDetail(
            requestedItemId,
            outputRoot,
            string.Empty,
            string.Empty,
            ex.Message);
    }

    var timelinePath = Path.Combine(itemDirectory, "timeline.json");
    var convertInfoPath = Path.Combine(itemDirectory, "convert_info.json");
    if (!File.Exists(timelinePath))
    {
        return NewUnavailableThreadDetail(
            requestedItemId,
            itemDirectory,
            timelinePath,
            convertInfoPath,
            "Thread was not found.");
    }

    var timeline = await ReadJsonFileAsync(timelinePath, cancellationToken);
    if (timeline is null)
    {
        return NewUnavailableThreadDetail(
            requestedItemId,
            itemDirectory,
            timelinePath,
            convertInfoPath,
            "Thread could not be read.",
            requestedItemId);
    }

    var messages = new JsonArray();
    var index = 0;
    foreach (var messageNode in GetArray(timeline, "messages"))
    {
        if (messageNode is JsonObject message)
        {
            messages.Add(ConvertThreadMessage(message, index));
        }

        index++;
    }

    var itemId = GetStringAnyOrDefault(timeline, itemIdNames, requestedItemId);
    var title = GetStringAnyOrDefault(timeline, ["title"], itemId);

    return new JsonObject
    {
        ["available"] = true,
        ["itemId"] = itemId,
        ["title"] = title,
        ["createdAt"] = GetStringAny(timeline, ["created_at", "createdAt"]),
        ["updatedAt"] = GetStringAny(timeline, ["updated_at", "updatedAt"]),
        ["messageCount"] = messages.Count,
        ["messages"] = messages,
        ["directoryPath"] = itemDirectory,
        ["timelinePath"] = timelinePath,
        ["convertInfoPath"] = convertInfoPath,
        ["message"] = string.Empty,
    };
}

static async Task<string> ResolveOutputRootAsync(ProductPaths paths, CancellationToken cancellationToken)
{
    var settings = await ReadJsonFileAsync(paths.SettingsPath, cancellationToken);
    var outputRootNode = GetNode(settings, "outputRoot");
    var outputRoot = outputRootNode is JsonObject outputRootObject
        ? GetStringAny(outputRootObject, ["path", "displayPath", "value"])
        : ConvertJsonText(outputRootNode);

    if (string.IsNullOrWhiteSpace(outputRoot))
    {
        return string.Empty;
    }

    return Path.GetFullPath(Path.IsPathRooted(outputRoot)
        ? outputRoot
        : Path.Combine(paths.ProductRoot, outputRoot));
}

static async Task<JsonObject?> ReadJsonFileAsync(string path, CancellationToken cancellationToken)
{
    if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
    {
        return null;
    }

    try
    {
        await using var stream = File.OpenRead(path);
        return await JsonNode.ParseAsync(stream, cancellationToken: cancellationToken) as JsonObject;
    }
    catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
    {
        return null;
    }
}

static JsonObject BuildAllPagination(int totalItems, int returnedItems)
    => new()
    {
        ["mode"] = "all",
        ["page"] = null,
        ["page_size"] = null,
        ["total_items"] = totalItems,
        ["total_pages"] = totalItems > 0 ? 1 : 0,
        ["returned_items"] = returnedItems,
        ["offset"] = 0,
        ["range_start"] = returnedItems > 0 ? 1 : 0,
        ["range_end"] = returnedItems,
        ["has_previous"] = false,
        ["has_next"] = false,
    };

static JsonObject BuildPagePagination(int page, int pageSize, int totalItems, int returnedItems)
{
    page = Math.Max(1, page);
    pageSize = Math.Max(1, pageSize);
    var offset = (page - 1) * pageSize;
    var totalPages = totalItems > 0
        ? (int)Math.Ceiling(totalItems / (double)pageSize)
        : 0;
    var rangeStart = returnedItems > 0 ? offset + 1 : 0;
    var rangeEnd = returnedItems > 0 ? offset + returnedItems : 0;
    return new JsonObject
    {
        ["mode"] = "page",
        ["page"] = page,
        ["page_size"] = pageSize,
        ["total_items"] = totalItems,
        ["total_pages"] = totalPages,
        ["returned_items"] = returnedItems,
        ["offset"] = offset,
        ["range_start"] = rangeStart,
        ["range_end"] = rangeEnd,
        ["has_previous"] = page > 1 && totalItems > 0,
        ["has_next"] = page < totalPages,
    };
}

static double ItemLatestTimestamp(JsonObject item)
{
    foreach (var name in new[] { "updated_at", "ended_at_utc", "created_at", "started_at_utc" })
    {
        var parsed = ParseSortTimestamp(GetNode(item, name));
        if (parsed is not null)
        {
            return parsed.Value;
        }
    }

    return double.NegativeInfinity;
}

static double? ParseSortTimestamp(JsonNode? node)
{
    if (node is null)
    {
        return null;
    }
    if (node is JsonValue value)
    {
        if (value.TryGetValue<double>(out var doubleValue))
        {
            return doubleValue;
        }
        if (value.TryGetValue<string>(out var textValue))
        {
            var text = textValue.Trim();
            if (double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var parsedNumber))
            {
                return parsedNumber;
            }
            if (DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var parsedDate))
            {
                return parsedDate.ToUnixTimeMilliseconds() / 1000.0;
            }
        }
    }

    return null;
}

static string ResolveDownloadDestination(string destinationText, JsonObject manifest)
{
    var destination = Path.GetFullPath(destinationText.Trim());
    if (Path.GetExtension(destination).Equals(".zip", StringComparison.OrdinalIgnoreCase))
    {
        return destination;
    }

    var runId = GetStringAny(manifest, ["run_id", "runId"]);
    if (string.IsNullOrWhiteSpace(runId))
    {
        runId = "latest";
    }

    return Path.Combine(destination, $"TimelineForChatGPT-export-{runId}.zip");
}

static string BuildChatGptDownloadReadme(JsonObject manifest)
{
    var source = GetNode(manifest, "source_export") as JsonObject;
    return string.Join(
        "\n",
        [
            "# TimelineForChatGPT Export",
            "",
            "This package was generated by TimelineForChatGPT from a ChatGPT export ZIP.",
            "",
            "Contents:",
            "",
            "- `README.md`: this file.",
            "- `items/<conversation_id>/convert_info.json`: conversion metadata for one conversation.",
            "- `items/<conversation_id>/timeline.json`: final exported title and user / assistant / system messages in conversation order.",
            "",
            $"- Generated at: `{GetStringAny(manifest, ["generated_at", "generatedAt"])}`",
            $"- Run ID: `{GetStringAny(manifest, ["run_id", "runId"])}`",
            $"- Source file: `{GetStringAny(source, ["filename"])}`",
            $"- Conversation count: `{GetIntAny(manifest, ["item_count", "itemCount"]) ?? 0}`",
            "",
        ]);
}

static void AddTextEntry(ZipArchive archive, string name, string text)
{
    var entry = archive.CreateEntry(name);
    using var stream = entry.Open();
    using var writer = new StreamWriter(stream, new UTF8Encoding(false));
    writer.Write(text);
}

static string ResolveInternalRuntimePath(string envName, string fallbackPath, string baseDirectory)
{
    var configured = Environment.GetEnvironmentVariable(envName);
    var path = string.IsNullOrWhiteSpace(configured) ? fallbackPath : configured;
    return Path.GetFullPath(Path.IsPathRooted(path)
        ? path
        : Path.Combine(baseDirectory, path));
}

static List<JsonNode?> GetArray(JsonObject? source, string name)
{
    var node = GetNode(source, name);
    return node is JsonArray array ? array.ToList() : [];
}

static JsonObject ConvertThreadMessage(JsonObject message, int index)
    => new()
    {
        ["index"] = index,
        ["role"] = GetStringAny(message, ["role"]),
        ["createdAt"] = GetStringAny(message, ["created_at", "createdAt"]),
        ["text"] = GetStringAny(message, ["text"]),
    };

static JsonObject NewUnavailableThreadDetail(
    string itemId,
    string directoryPath,
    string timelinePath,
    string convertInfoPath,
    string message,
    string title = "")
    => new()
    {
        ["available"] = false,
        ["itemId"] = itemId,
        ["title"] = title,
        ["createdAt"] = string.Empty,
        ["updatedAt"] = string.Empty,
        ["messageCount"] = 0,
        ["messages"] = new JsonArray(),
        ["directoryPath"] = directoryPath,
        ["timelinePath"] = timelinePath,
        ["convertInfoPath"] = convertInfoPath,
        ["message"] = message,
    };

static string GetSafeChildDirectory(string rootPath, string childName)
{
    var fullRoot = Path.GetFullPath(rootPath);
    var safeRootPrefix = fullRoot.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
    var normalizedChild = childName.Replace('/', Path.DirectorySeparatorChar).Replace('\\', Path.DirectorySeparatorChar);
    var fullCandidate = Path.GetFullPath(Path.Combine(fullRoot, normalizedChild));
    if (!fullCandidate.StartsWith(safeRootPrefix, StringComparison.OrdinalIgnoreCase))
    {
        throw new InvalidOperationException("Invalid item id.");
    }

    return fullCandidate;
}

static JsonObject ErrorPayload(string message)
{
    return new JsonObject
    {
        ["ok"] = false,
        ["error"] = new JsonObject
        {
            ["message"] = message,
        },
    };
}

static void AddOptionalValue(List<string> arguments, string name, string value)
{
    if (string.IsNullOrWhiteSpace(value))
    {
        return;
    }

    arguments.Add(name);
    arguments.Add(value.Trim());
}

static string GetStringAny(JsonObject? source, string[] names)
{
    foreach (var name in names)
    {
        var node = GetNode(source, name);
        if (node is not null)
        {
            return ConvertJsonText(node);
        }
    }

    return string.Empty;
}

static string GetStringAnyOrDefault(JsonObject? source, string[] names, string fallback)
{
    var value = GetStringAny(source, names);
    return string.IsNullOrEmpty(value) ? fallback : value;
}

static int? GetIntAny(JsonObject? source, string[] names)
{
    foreach (var name in names)
    {
        var node = GetNode(source, name);
        if (node is null)
        {
            continue;
        }

        if (node is JsonValue value)
        {
            if (value.TryGetValue<int>(out var intValue))
            {
                return intValue;
            }
            if (value.TryGetValue<string>(out var textValue)
                && int.TryParse(textValue, NumberStyles.Integer, CultureInfo.InvariantCulture, out var parsed))
            {
                return parsed;
            }
        }
    }

    return null;
}

static bool GetBoolAny(JsonObject? source, string[] names, bool fallback)
{
    foreach (var name in names)
    {
        var node = GetNode(source, name);
        if (node is not JsonValue value)
        {
            continue;
        }

        if (value.TryGetValue<bool>(out var boolValue))
        {
            return boolValue;
        }
        if (value.TryGetValue<string>(out var textValue))
        {
            var text = textValue.Trim().ToLowerInvariant();
            if (text is "1" or "true" or "yes" or "on")
            {
                return true;
            }
            if (text is "0" or "false" or "no" or "off")
            {
                return false;
            }
        }
    }

    return fallback;
}

static JsonNode? GetNode(JsonObject? source, string name)
{
    if (source is null)
    {
        return null;
    }
    if (source.TryGetPropertyValue(name, out var node))
    {
        return node;
    }

    foreach (var property in source)
    {
        if (property.Key.Equals(name, StringComparison.OrdinalIgnoreCase))
        {
            return property.Value;
        }
    }

    return null;
}

static string ConvertJsonText(JsonNode? node)
{
    if (node is null)
    {
        return string.Empty;
    }
    if (node is JsonValue value)
    {
        if (value.TryGetValue<string>(out var text))
        {
            return text.Trim();
        }
        if (value.TryGetValue<int>(out var intValue))
        {
            return intValue.ToString(CultureInfo.InvariantCulture);
        }
        if (value.TryGetValue<bool>(out var boolValue))
        {
            return boolValue ? "true" : "false";
        }
    }

    return node.ToJsonString();
}

public sealed record ProductPaths(
    string ProductRoot,
    string SettingsPath,
    string SettingsExamplePath,
    string DockerComposePath)
{
    public static ProductPaths Resolve(string[] args)
    {
        var productRoot = ArgValue(args, "--product-root");
        if (string.IsNullOrWhiteSpace(productRoot))
        {
            productRoot = Environment.GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_PRODUCT_ROOT");
        }
        if (string.IsNullOrWhiteSpace(productRoot))
        {
            productRoot = Directory.GetCurrentDirectory();
        }

        productRoot = Path.GetFullPath(productRoot);
        var settingsPath = Environment.GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_SETTINGS")
            ?? Environment.GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_HOST_SETTINGS_PATH")
            ?? Path.Combine(productRoot, "settings.json");
        if (!Path.IsPathRooted(settingsPath))
        {
            settingsPath = Path.Combine(productRoot, settingsPath);
        }

        return new ProductPaths(
            productRoot,
            Path.GetFullPath(settingsPath),
            Path.Combine(productRoot, "settings.example.json"),
            Path.Combine(productRoot, "docker-compose.yml"));
    }

    public static int ReadPort(string[] args, string settingsPath, int fallback)
    {
        var configured = ArgValue(args, "--port")
            ?? Environment.GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_API_LISTEN_PORT")
            ?? Environment.GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_API_PORT")
            ?? ReadApiPort(settingsPath);

        return int.TryParse(configured, NumberStyles.Integer, CultureInfo.InvariantCulture, out var port)
            && port is >= 1 and <= 65535
            ? port
            : fallback;
    }

    public static string? ArgValue(string[] args, string name)
    {
        for (var index = 0; index < args.Length; index += 1)
        {
            if (args[index].Equals(name, StringComparison.OrdinalIgnoreCase)
                && index + 1 < args.Length)
            {
                return args[index + 1];
            }
            if (args[index].StartsWith(name + "=", StringComparison.OrdinalIgnoreCase))
            {
                return args[index][(name.Length + 1)..];
            }
        }

        return null;
    }

    public static bool IsValidPort(JsonElement apiPort)
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

    private static string? ReadApiPort(string settingsPath)
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
}

public sealed class ProductCommandException : Exception
{
    public ProductCommandException(string message, int exitCode, JsonNode? payload)
        : base(message)
    {
        ExitCode = exitCode;
        Payload = payload;
    }

    public int ExitCode { get; }

    public JsonNode? Payload { get; }
}

public sealed class ProductCommandRunner
{
    private readonly ProductPaths _paths;

    public ProductCommandRunner(ProductPaths paths)
    {
        _paths = paths;
    }

    public async Task<JsonNode?> RunJsonAsync(
        IReadOnlyList<string> arguments,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        var runtime = ChatGptRuntime.Ensure(_paths);
        var dockerPath = ResolveDockerCommand();
        var composeArguments = BuildComposeArguments(runtime);
        var containerId = await GetWorkerContainerIdAsync(dockerPath, composeArguments, runtime, timeout, cancellationToken);
        if (string.IsNullOrWhiteSpace(containerId))
        {
            throw new InvalidOperationException("TimelineForChatGPT worker is not running.");
        }

        var converted = await ConvertArgumentsAsync(
            dockerPath,
            containerId,
            arguments,
            runtime,
            timeout,
            cancellationToken);
        var replacements = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["/workspace/output/"] = runtime.OutputRoot.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar,
            ["/workspace/output"] = runtime.OutputRoot,
        };

        try
        {
            var dockerArguments = new List<string>
            {
                "compose",
            };
            dockerArguments.AddRange(composeArguments);
            dockerArguments.AddRange([
                "exec",
                "-T",
                "worker",
                "python",
                "-m",
                "timeline_for_chatgpt_worker",
            ]);
            dockerArguments.AddRange(converted.Arguments);

            var result = await RunProcessAsync(
                dockerPath,
                dockerArguments,
                _paths.ProductRoot,
                runtime,
                timeout,
                cancellationToken);
            var stdout = result.Stdout;
            var stderr = result.Stderr;

            if (result.ExitCode == 0 && converted.OutputPlans.Count > 0)
            {
                foreach (var replacement in await CopyOutputsAsync(
                    dockerPath,
                    containerId,
                    converted.OutputPlans,
                    runtime,
                    timeout,
                    cancellationToken))
                {
                    replacements[replacement.Key] = replacement.Value;
                }
            }

            stdout = ApplyReplacements(stdout, replacements);
            stderr = ApplyReplacements(stderr, replacements);
            var payload = TryParseJson(stdout) ?? TryParseJson(stderr);
            if (result.ExitCode != 0)
            {
                var message = GetErrorMessage(payload);
                if (string.IsNullOrWhiteSpace(message))
                {
                    message = !string.IsNullOrWhiteSpace(stderr)
                        ? stderr.Trim()
                        : !string.IsNullOrWhiteSpace(stdout)
                            ? stdout.Trim()
                            : $"exit code {result.ExitCode}";
                }

                throw new ProductCommandException(message, result.ExitCode, payload);
            }

            if (payload is null)
            {
                throw new InvalidOperationException("TimelineForChatGPT command did not return JSON.");
            }

            return payload;
        }
        finally
        {
            await RemoveTempRootsAsync(dockerPath, containerId, converted.TempRoots, runtime, TimeSpan.FromSeconds(30), CancellationToken.None);
        }
    }

    private async Task<string> GetWorkerContainerIdAsync(
        string dockerPath,
        IReadOnlyList<string> composeArguments,
        ChatGptRuntime runtime,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        var arguments = new List<string>
        {
            "compose",
        };
        arguments.AddRange(composeArguments);
        arguments.AddRange(["ps", "-q", "worker"]);

        var result = await RunProcessAsync(
            dockerPath,
            arguments,
            _paths.ProductRoot,
            runtime,
            timeout,
            cancellationToken);
        if (result.ExitCode != 0)
        {
            var message = !string.IsNullOrWhiteSpace(result.Stderr)
                ? result.Stderr.Trim()
                : !string.IsNullOrWhiteSpace(result.Stdout)
                    ? result.Stdout.Trim()
                    : "TimelineForChatGPT worker status could not be checked.";
            throw new InvalidOperationException(message);
        }

        return result.Stdout.Trim();
    }

    private static IReadOnlyList<string> BuildComposeArguments(ChatGptRuntime runtime)
        => ["-p", runtime.ComposeProject];

    private async Task<ConvertedArguments> ConvertArgumentsAsync(
        string dockerPath,
        string containerId,
        IReadOnlyList<string> inputArguments,
        ChatGptRuntime runtime,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        var converted = new List<string>();
        var tempRoots = new List<string>();
        var outputPlans = new List<OutputPlan>();
        var overwrite = inputArguments.Contains("--overwrite", StringComparer.Ordinal);

        for (var index = 0; index < inputArguments.Count; index++)
        {
            var argument = inputArguments[index];
            if (argument == "--file" && index + 1 < inputArguments.Count)
            {
                var rawPath = inputArguments[index + 1];
                converted.Add(argument);
                if (IsContainerPath(rawPath))
                {
                    converted.Add(rawPath);
                }
                else
                {
                    var hostPath = ResolveHostPath(rawPath, requireExisting: true);
                    var tempRoot = NewContainerTempRoot("uploads");
                    var containerPath = $"{tempRoot}/{SafeContainerFileName(hostPath)}";
                    await RunDockerCheckedAsync(dockerPath, ["exec", containerId, "mkdir", "-p", tempRoot], runtime, timeout, cancellationToken);
                    await RunDockerCheckedAsync(dockerPath, ["cp", hostPath, $"{containerId}:{containerPath}"], runtime, timeout, cancellationToken);
                    converted.Add(containerPath);
                    tempRoots.Add(tempRoot);
                }
                index += 1;
                continue;
            }

            if ((argument == "--download-to" || argument == "--to") && index + 1 < inputArguments.Count)
            {
                var rawPath = inputArguments[index + 1];
                converted.Add(argument);
                if (IsContainerPath(rawPath))
                {
                    converted.Add(rawPath);
                }
                else
                {
                    var hostPath = ResolveHostPath(rawPath, requireExisting: false);
                    var tempRoot = NewContainerTempRoot("handoff");
                    await RunDockerCheckedAsync(dockerPath, ["exec", containerId, "mkdir", "-p", tempRoot], runtime, timeout, cancellationToken);
                    var isZip = string.Equals(Path.GetExtension(hostPath), ".zip", StringComparison.OrdinalIgnoreCase);
                    var containerPath = isZip ? $"{tempRoot}/{SafeContainerFileName(hostPath)}" : tempRoot;
                    if (isZip)
                    {
                        var parent = Path.GetDirectoryName(hostPath);
                        if (!string.IsNullOrWhiteSpace(parent))
                        {
                            Directory.CreateDirectory(parent);
                        }
                        if (File.Exists(hostPath) && !overwrite)
                        {
                            throw new InvalidOperationException($"Download target already exists: {hostPath}");
                        }
                    }
                    else
                    {
                        Directory.CreateDirectory(hostPath);
                    }
                    converted.Add(containerPath);
                    tempRoots.Add(tempRoot);
                    outputPlans.Add(new OutputPlan(hostPath, containerPath, tempRoot, isZip, overwrite));
                }
                index += 1;
                continue;
            }

            converted.Add(argument);
        }

        return new ConvertedArguments(converted, tempRoots, outputPlans);
    }

    private static async Task<IReadOnlyDictionary<string, string>> CopyOutputsAsync(
        string dockerPath,
        string containerId,
        IReadOnlyList<OutputPlan> outputPlans,
        ChatGptRuntime runtime,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        var replacements = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var plan in outputPlans)
        {
            if (plan.IsZip)
            {
                await RunDockerCheckedAsync(dockerPath, ["cp", $"{containerId}:{plan.ContainerPath}", plan.HostPath], runtime, timeout, cancellationToken);
                replacements[plan.ContainerPath] = plan.HostPath;
                continue;
            }

            var findResult = await RunProcessAsync(
                dockerPath,
                ["exec", containerId, "find", plan.ContainerPath, "-maxdepth", "1", "-type", "f", "-name", "*.zip", "-print"],
                Directory.GetCurrentDirectory(),
                runtime,
                timeout,
                cancellationToken);
            if (findResult.ExitCode != 0)
            {
                throw new InvalidOperationException($"Failed to inspect container output directory: {plan.ContainerPath}");
            }

            foreach (var zipPath in findResult.Stdout.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                var hostZipPath = Path.Combine(plan.HostPath, Path.GetFileName(zipPath));
                if (File.Exists(hostZipPath) && !plan.Overwrite)
                {
                    throw new InvalidOperationException($"Download target already exists: {hostZipPath}");
                }
                replacements[zipPath] = hostZipPath;
            }
            await RunDockerCheckedAsync(dockerPath, ["cp", $"{containerId}:{plan.ContainerPath}/.", plan.HostPath], runtime, timeout, cancellationToken);
        }
        return replacements;
    }

    private static async Task RemoveTempRootsAsync(
        string dockerPath,
        string containerId,
        IReadOnlyList<string> tempRoots,
        ChatGptRuntime runtime,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        foreach (var tempRoot in tempRoots.Where(value => !string.IsNullOrWhiteSpace(value)))
        {
            try
            {
                await RunProcessAsync(
                    dockerPath,
                    ["exec", containerId, "rm", "-rf", tempRoot],
                    Directory.GetCurrentDirectory(),
                    runtime,
                    timeout,
                    cancellationToken);
            }
            catch
            {
            }
        }
    }

    private static async Task RunDockerCheckedAsync(
        string dockerPath,
        IReadOnlyList<string> arguments,
        ChatGptRuntime runtime,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        var result = await RunProcessAsync(dockerPath, arguments, Directory.GetCurrentDirectory(), runtime, timeout, cancellationToken);
        if (result.ExitCode != 0)
        {
            var message = !string.IsNullOrWhiteSpace(result.Stderr)
                ? result.Stderr.Trim()
                : !string.IsNullOrWhiteSpace(result.Stdout)
                    ? result.Stdout.Trim()
                    : $"docker command failed with exit code {result.ExitCode}.";
            throw new InvalidOperationException(message);
        }
    }

    private static async Task<CommandResult> RunProcessAsync(
        string fileName,
        IReadOnlyList<string> arguments,
        string workingDirectory,
        ChatGptRuntime runtime,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = fileName,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        startInfo.Environment["COMPOSE_PROJECT_NAME"] = runtime.ComposeProject;
        startInfo.Environment["TIMELINE_FOR_CHATGPT_INSTANCE_NAME"] = runtime.InstanceName;
        startInfo.Environment["TIMELINE_FOR_CHATGPT_API_PORT"] = runtime.ApiPort.ToString(CultureInfo.InvariantCulture);
        startInfo.Environment["TIMELINE_FOR_CHATGPT_HOST_SETTINGS_PATH"] = runtime.SettingsPath;
        startInfo.Environment["TIMELINE_FOR_CHATGPT_SETTINGS"] = runtime.SettingsPath;
        startInfo.Environment["TIMELINE_FOR_CHATGPT_HOST_OUTPUT_ROOT"] = runtime.OutputRoot;
        foreach (var argument in arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        using var process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("TimelineForChatGPT command process could not be started.");
        var stdoutTask = process.StandardOutput.ReadToEndAsync();
        var stderrTask = process.StandardError.ReadToEndAsync();

        using var timeoutSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutSource.CancelAfter(timeout);
        try
        {
            await process.WaitForExitAsync(timeoutSource.Token);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            KillProcessTree(process);
            throw new TimeoutException($"TimelineForChatGPT command timed out after {(int)timeout.TotalSeconds} seconds.");
        }
        catch
        {
            KillProcessTree(process);
            throw;
        }

        var stdout = await stdoutTask;
        var stderr = await stderrTask;
        return new CommandResult(process.ExitCode, stdout, stderr);
    }

    private static void KillProcessTree(Process process)
    {
        try
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
            }
        }
        catch
        {
        }
    }

    private static JsonNode? TryParseJson(string text)
    {
        var trimmed = text.Trim();
        if (string.IsNullOrEmpty(trimmed))
        {
            return null;
        }

        try
        {
            return JsonNode.Parse(trimmed);
        }
        catch (JsonException)
        {
        }

        var objectStart = trimmed.IndexOf('{');
        var objectEnd = trimmed.LastIndexOf('}');
        if (objectStart >= 0 && objectEnd > objectStart)
        {
            try
            {
                return JsonNode.Parse(trimmed[objectStart..(objectEnd + 1)]);
            }
            catch (JsonException)
            {
            }
        }

        return null;
    }

    private static string GetErrorMessage(JsonNode? payload)
    {
        if (payload is not JsonObject obj)
        {
            return string.Empty;
        }

        if (obj["error"] is JsonObject error
            && error["message"] is JsonValue errorMessage
            && errorMessage.TryGetValue<string>(out var message)
            && !string.IsNullOrWhiteSpace(message))
        {
            return message.Trim();
        }

        if (obj["message"] is JsonValue messageValue
            && messageValue.TryGetValue<string>(out var rootMessage)
            && !string.IsNullOrWhiteSpace(rootMessage))
        {
            return rootMessage.Trim();
        }

        return string.Empty;
    }

    private static string ResolveDockerCommand()
    {
        var programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        if (!string.IsNullOrWhiteSpace(programFiles))
        {
            var dockerExe = Path.Combine(programFiles, "Docker", "Docker", "resources", "bin", "docker.exe");
            if (File.Exists(dockerExe))
            {
                return dockerExe;
            }
        }

        return "docker";
    }

    private static string ApplyReplacements(string text, IReadOnlyDictionary<string, string> replacements)
    {
        var result = text;
        var jsonLike = result.TrimStart().StartsWith("{", StringComparison.Ordinal)
            || result.TrimStart().StartsWith("[", StringComparison.Ordinal);
        foreach (var replacement in replacements.OrderByDescending(row => row.Key.Length))
        {
            var value = jsonLike ? replacement.Value.Replace("\\", "\\\\", StringComparison.Ordinal) : replacement.Value;
            result = result.Replace(replacement.Key, value, StringComparison.Ordinal);
        }
        return result;
    }

    private static bool IsContainerPath(string value)
        => value.TrimStart().StartsWith("/", StringComparison.Ordinal);

    private string ResolveHostPath(string value, bool requireExisting)
    {
        var candidate = value.Trim().Trim('"', '\'');
        if (!Path.IsPathRooted(candidate))
        {
            candidate = Path.Combine(_paths.ProductRoot, candidate);
        }
        var fullPath = Path.GetFullPath(candidate);
        if (requireExisting && !File.Exists(fullPath) && !Directory.Exists(fullPath))
        {
            throw new FileNotFoundException($"Path was not found: {fullPath}", fullPath);
        }
        return fullPath;
    }

    private static string NewContainerTempRoot(string kind)
        => $"/tmp/timeline-for-chatgpt/api/{kind}-{Guid.NewGuid():N}";

    private static string SafeContainerFileName(string path)
    {
        var safe = Path.GetFileName(path);
        if (string.IsNullOrWhiteSpace(safe))
        {
            return "input.zip";
        }
        safe = safe.Replace("\\", "_", StringComparison.Ordinal).Replace("/", "_", StringComparison.Ordinal).Replace(":", "_", StringComparison.Ordinal);
        return safe.Length <= 80 ? safe : $"input-{Guid.NewGuid():N}{Path.GetExtension(safe)}";
    }
}

internal sealed record CommandResult(int ExitCode, string Stdout, string Stderr);

internal sealed record ConvertedArguments(
    IReadOnlyList<string> Arguments,
    IReadOnlyList<string> TempRoots,
    IReadOnlyList<OutputPlan> OutputPlans);

internal sealed record OutputPlan(string HostPath, string ContainerPath, string ContainerRoot, bool IsZip, bool Overwrite);

internal sealed record ChatGptRuntime(
    string InstanceName,
    int ApiPort,
    string ComposeProject,
    string SettingsPath,
    string OutputRoot)
{
    public static ChatGptRuntime Ensure(ProductPaths paths)
    {
        EnsureSettingsFile(paths);
        var settings = JsonNode.Parse(File.ReadAllText(paths.SettingsPath, Encoding.UTF8)) as JsonObject ?? new JsonObject();
        var runtime = settings["runtime"] as JsonObject ?? new JsonObject();

        var instanceName = SafeName(Environment.GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_INSTANCE_NAME") ?? GetString(runtime, "instanceName"));
        var apiPort = TryParsePort(Environment.GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_API_PORT"))
            ?? GetInt(runtime, "apiPort")
            ?? 19300;
        if (apiPort is < 1 or > 65535)
        {
            apiPort = 19300;
        }

        var composeProject = Environment.GetEnvironmentVariable("COMPOSE_PROJECT_NAME");
        if (string.IsNullOrWhiteSpace(composeProject))
        {
            composeProject = Environment.GetEnvironmentVariable("TIMELINE_FOR_CHATGPT_COMPOSE_PROJECT");
        }
        if (string.IsNullOrWhiteSpace(composeProject))
        {
            composeProject = string.IsNullOrWhiteSpace(instanceName)
                ? "timeline-for-chatgpt"
                : $"timeline-for-chatgpt-{instanceName}";
        }

        var outputRoot = GetString(settings, "outputRoot");
        if (string.IsNullOrWhiteSpace(outputRoot))
        {
            outputRoot = @"C:\TimelineData\chatgpt";
        }
        if (!Path.IsPathRooted(outputRoot))
        {
            outputRoot = Path.Combine(paths.ProductRoot, outputRoot);
        }
        outputRoot = Path.GetFullPath(outputRoot);
        Directory.CreateDirectory(outputRoot);

        return new ChatGptRuntime(instanceName, apiPort, composeProject, paths.SettingsPath, outputRoot);
    }

    private static void EnsureSettingsFile(ProductPaths paths)
    {
        if (File.Exists(paths.SettingsPath))
        {
            return;
        }

        var settingsDirectory = Path.GetDirectoryName(paths.SettingsPath);
        if (!string.IsNullOrWhiteSpace(settingsDirectory))
        {
            Directory.CreateDirectory(settingsDirectory);
        }

        if (File.Exists(paths.SettingsExamplePath))
        {
            File.Copy(paths.SettingsExamplePath, paths.SettingsPath, overwrite: true);
            return;
        }

        File.WriteAllText(
            paths.SettingsPath,
            """
            {
              "schemaVersion": 1,
              "runtime": {
                "instanceName": "",
                "apiPort": 19300
              },
              "outputRoot": "C:\\TimelineData\\chatgpt"
            }
            """,
            new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
    }

    private static string SafeName(string value)
    {
        var builder = new StringBuilder();
        var lastWasDash = false;
        foreach (var ch in value.Trim().ToLowerInvariant())
        {
            var isValid = ch is >= 'a' and <= 'z' || ch is >= '0' and <= '9';
            if (isValid)
            {
                builder.Append(ch);
                lastWasDash = false;
            }
            else if (!lastWasDash)
            {
                builder.Append('-');
                lastWasDash = true;
            }
        }
        var text = builder.ToString().Trim('-');
        return text.Length > 48 ? text[..48].Trim('-') : text;
    }

    private static string GetString(JsonObject source, string name)
    {
        if (source[name] is JsonValue value && value.TryGetValue<string>(out var text))
        {
            return text.Trim();
        }
        return string.Empty;
    }

    private static int? GetInt(JsonObject source, string name)
    {
        if (source[name] is not JsonValue value)
        {
            return null;
        }
        if (value.TryGetValue<int>(out var intValue))
        {
            return intValue;
        }
        if (value.TryGetValue<string>(out var textValue) && int.TryParse(textValue, out var parsed))
        {
            return parsed;
        }
        return null;
    }

    private static int? TryParsePort(string? value)
    {
        if (string.IsNullOrWhiteSpace(value) || !int.TryParse(value, out var port))
        {
            return null;
        }
        return port is >= 1 and <= 65535 ? port : null;
    }
}
