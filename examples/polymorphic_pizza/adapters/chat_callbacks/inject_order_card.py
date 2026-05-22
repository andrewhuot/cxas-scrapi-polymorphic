# pylint: disable=invalid-name,undefined-variable,unused-argument,broad-exception-caught,line-too-long
"""Before-model callback — chat order-card hints.

Channel-specific (chat) callback added by the polymorphism engine. Nudges
the model to render the final order with the send_order_card tool so the
customer gets a visual confirmation card instead of plain text.
"""

from typing import Optional


def before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
  """Inject a hint to use the order card when confirming."""
  hint = (
      "When the order is complete, call send_order_card to render a "
      "confirmation card with the order summary, the total, and "
      "Confirm / Edit action buttons."
  )
  try:
    llm_request.append_instructions([hint])
  except Exception:
    pass

  return None
