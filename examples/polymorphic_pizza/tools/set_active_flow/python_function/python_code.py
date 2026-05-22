"""Activate a flow and route to the matching specialist agent.

Setter tool for the root Pizza Host. When called, the host's after_tool
callback records the target agent and the before_model callback fires a
deterministic transfer to it.
"""

from typing import Any


_VALID_FLOWS = {"order", "track"}

_FLOW_TO_AGENT = {
    "order": "Order_Agent",
    "track": "Tracking_Agent",
}


def set_active_flow(flow: str) -> dict[str, Any]:
  """Activate a flow and route to the right specialist.

  Args:
    flow: The flow to activate — 'order' or 'track'.

  Returns:
    Dict with stored=True, the normalized value, and the target agent on
    success, or error=True on failure.
  """
  flow = str(flow).lower().strip()
  if flow not in _VALID_FLOWS:
    return {"error": True, "error_code": "invalid_flow"}
  result = {"stored": True, "value": flow}
  target = _FLOW_TO_AGENT.get(flow)
  if target:
    result["target_agent"] = target
  return result
