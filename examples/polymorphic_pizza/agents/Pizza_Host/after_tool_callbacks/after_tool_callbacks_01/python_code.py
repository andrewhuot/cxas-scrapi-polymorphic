# pylint: disable=invalid-name,undefined-variable,unused-argument,broad-exception-caught,line-too-long
"""After-tool callback — transfer routing.

When set_active_flow is called on the Pizza Host, record the target
specialist in _pending_transfer so the before_model callback can fire the
agent transfer on the next model call.
"""

from typing import Any, Optional


def after_tool_callback(
    tool: Tool,
    tool_input: dict[str, Any],
    callback_context: CallbackContext,
    tool_response: dict[str, Any],
) -> Optional[dict[str, Any]]:
  """Capture set_active_flow result and prepare the transfer."""
  if tool.name != "set_active_flow":
    return None

  result = tool_response.get("result", tool_response)
  if not result.get("stored"):
    return None

  target = result.get("target_agent")
  if target:
    callback_context.state["_pending_transfer"] = target

  return None
