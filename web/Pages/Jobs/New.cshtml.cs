using TimelineForChatGPT.Web.Localization;
using TimelineForChatGPT.Web.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace TimelineForChatGPT.Web.Pages.Jobs;

public sealed class NewModel(RunStore runStore, UiText text) : PageModel
{
    [BindProperty]
    public IFormFile? UploadFile { get; set; }

    [BindProperty]
    public bool ReprocessDuplicates { get; set; }

    [TempData]
    public string? StatusMessage { get; set; }

    public async Task<IActionResult> OnPostAsync(CancellationToken cancellationToken)
    {
        if (UploadFile is null)
        {
            ModelState.AddModelError(nameof(UploadFile), text["Validation.SelectExportZip"]);
            return Page();
        }

        try
        {
            var saved = await runStore.SaveUploadAsync(UploadFile, cancellationToken);
            var created = await runStore.CreateJobAsync(saved, ReprocessDuplicates, cancellationToken);
            return RedirectToPage("/Runs/Details", new { id = created.JobId });
        }
        catch (InvalidOperationException ex)
        {
            ModelState.AddModelError(string.Empty, ex.Message);
            return Page();
        }
    }
}
