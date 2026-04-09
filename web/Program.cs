using System.Globalization;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.Localization;
using TimelineForChatGPT.Web.Services;
using TimelineForChatGPT.Web.Localization;

var builder = WebApplication.CreateBuilder(args);
var appPaths = new AppPaths(builder.Configuration);
const long MaxUploadBytes = 4L * 1024 * 1024 * 1024;
var supportedCultures = new[] { new CultureInfo("ja"), new CultureInfo("en") };

Directory.CreateDirectory(appPaths.AppDataRoot);
Directory.CreateDirectory(appPaths.UploadsRoot);
Directory.CreateDirectory(appPaths.OutputsRoot);

builder.WebHost.ConfigureKestrel(options =>
{
    options.Limits.MaxRequestBodySize = MaxUploadBytes;
});

builder.Services.AddHttpContextAccessor();
builder.Services.AddSingleton<UiText>();
builder.Services.Configure<RequestLocalizationOptions>(options =>
{
    options.DefaultRequestCulture = new RequestCulture("ja");
    options.SupportedCultures = supportedCultures;
    options.SupportedUICultures = supportedCultures;
    options.RequestCultureProviders =
    [
        new CookieRequestCultureProvider(),
        new QueryStringRequestCultureProvider(),
        new AcceptLanguageHeaderRequestCultureProvider(),
    ];
});

builder.Services.AddRazorPages();
builder.Services.Configure<FormOptions>(options =>
{
    options.MultipartBodyLengthLimit = MaxUploadBytes;
});
builder.Services.AddSingleton(appPaths);
builder.Services.AddSingleton<SettingsStore>();
builder.Services.AddSingleton<RunStore>();

var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error");
}

app.UseRequestLocalization(app.Services.GetRequiredService<Microsoft.Extensions.Options.IOptions<RequestLocalizationOptions>>().Value);
app.UseRouting();
app.UseAuthorization();

app.MapGet("/set-language", (string culture, string? returnUrl, HttpContext httpContext) =>
{
    var normalizedCulture = supportedCultures.Any(item => string.Equals(item.Name, culture, StringComparison.OrdinalIgnoreCase))
        ? culture
        : "ja";

    httpContext.Response.Cookies.Append(
        CookieRequestCultureProvider.DefaultCookieName,
        CookieRequestCultureProvider.MakeCookieValue(new RequestCulture(normalizedCulture)),
        new CookieOptions
        {
            Expires = DateTimeOffset.UtcNow.AddYears(1),
            IsEssential = true,
            Path = "/",
        });

    if (string.IsNullOrWhiteSpace(returnUrl) || !Uri.IsWellFormedUriString(returnUrl, UriKind.Relative))
    {
        returnUrl = "/jobs";
    }

    return Results.LocalRedirect(returnUrl);
});

app.MapGet("/health", () => Results.Ok(new
{
    status = "ok",
    service = "timeline-for-chatgpt-web",
    timestamp = DateTimeOffset.UtcNow,
}));

app.MapGet("/jobs/{id}/download", async (string id, RunStore runStore, CancellationToken cancellationToken) =>
{
    var archivePath = await runStore.BuildRunArchiveAsync(id, cancellationToken);
    return string.IsNullOrWhiteSpace(archivePath)
        ? Results.NotFound()
        : Results.File(archivePath, "application/zip", Path.GetFileName(archivePath));
});

app.MapStaticAssets();
app.MapRazorPages()
    .WithStaticAssets();

app.Run();
