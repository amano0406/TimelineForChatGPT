using TimelineForChatGPT.Web.Models;
using TimelineForChatGPT.Web.Services;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace TimelineForChatGPT.Web.Pages.Jobs;

public sealed class IndexModel(RunStore runStore) : PageModel
{
    public RunSummary? ActiveRun { get; private set; }

    public IReadOnlyList<RunSummary> RecentRuns { get; private set; } = [];

    public async Task OnGetAsync(CancellationToken cancellationToken)
    {
        ActiveRun = await runStore.GetActiveRunAsync(cancellationToken);
        RecentRuns = await runStore.ListRunsAsync(cancellationToken);
    }
}
