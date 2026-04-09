using TimelineForChatGPT.Web.Models;
using TimelineForChatGPT.Web.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace TimelineForChatGPT.Web.Pages.Runs;

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
