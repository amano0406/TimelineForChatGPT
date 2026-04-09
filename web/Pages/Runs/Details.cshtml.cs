using TimelineForChatGPT.Web.Models;
using TimelineForChatGPT.Web.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace TimelineForChatGPT.Web.Pages.Runs;

public sealed class DetailsModel(RunStore runStore) : PageModel
{
    public RunDetails? Run { get; private set; }

    public async Task<IActionResult> OnGetAsync(string id, CancellationToken cancellationToken)
    {
        Run = await runStore.GetRunDetailsAsync(id, cancellationToken);
        return Run is null ? NotFound() : Page();
    }
}
