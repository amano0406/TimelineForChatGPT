using ChatGpt2Timeline.Web.Models;
using ChatGpt2Timeline.Web.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace ChatGpt2Timeline.Web.Pages.Runs;

public sealed class ConversationModel(RunStore runStore) : PageModel
{
    public ConversationDetails? Conversation { get; private set; }

    public async Task<IActionResult> OnGetAsync(
        string id,
        string conversationId,
        CancellationToken cancellationToken)
    {
        Conversation = await runStore.GetConversationDetailsAsync(id, conversationId, cancellationToken);
        return Conversation is null ? NotFound() : Page();
    }
}
