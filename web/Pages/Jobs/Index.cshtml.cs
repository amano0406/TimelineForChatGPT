using ChatGpt2Timeline.Web.Models;
using ChatGpt2Timeline.Web.Services;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace ChatGpt2Timeline.Web.Pages.Jobs;

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
