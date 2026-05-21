# pylint: disable=invalid-name,undefined-variable,unused-argument,broad-exception-caught,line-too-long
"""Before-model callback — chat rich-content hints.

Channel-specific (chat) callback added by the polymorphism engine. When the
conversation looks like it is about to confirm a reservation or order, it
nudges the model to render a structured rich card via the send_rich_card
tool instead of plain text.
"""

from typing import Optional


def before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
  """Inject a system hint to use rich card formatting on confirmation."""
  sm = callback_context.state.get("sm", {})
  pending = sm.get("pending", {}) if isinstance(sm, dict) else {}

  if pending:
    hint = (
        "When confirming details with the guest, call send_rich_card to "
        "render a confirmation card with a title, the reservation summary, "
        "and Confirm / Change action buttons."
    )
    try:
      llm_request.append_instructions([hint])
    except Exception:
      pass

  return None
