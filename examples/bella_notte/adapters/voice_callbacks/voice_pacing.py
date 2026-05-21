# pylint: disable=invalid-name,undefined-variable,unused-argument,broad-exception-caught,line-too-long
"""Before-model callback — voice pacing hints.

Channel-specific (voice) callback added by the polymorphism engine. Reminds
the model to keep spoken turns short and to emit a brief filler phrase
before long-running tool calls so the caller is not left in silence.
"""

from typing import Optional


def before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[LlmResponse]:
  """Inject voice pacing and filler-phrase hints before each model call."""
  hint = (
      "Spoken channel: respond in two to three short sentences, no markup. "
      "Before any tool call, say a brief filler such as "
      "'Let me check that for you...' so the line is never silent."
  )
  try:
    llm_request.append_instructions([hint])
  except Exception:
    pass

  return None
