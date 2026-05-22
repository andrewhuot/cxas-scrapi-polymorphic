"""Look up the status of an existing order.

Deterministic mock: the order number maps to a fixed stage so the demo is
reproducible without a real order database.
"""

import hashlib
from typing import Any


_STAGES = [
    ("received", "We have your order and the kitchen is starting on it.", 35),
    ("in the oven", "Your pizza is baking right now.", 18),
    ("out for delivery", "Your pizza is on its way to you.", 8),
    ("ready for pickup", "Your pizza is ready at the counter.", 0),
]


def get_order_status(order_number: str) -> dict[str, Any]:
  """Return the current status of an order.

  Args:
    order_number: The order number to look up, e.g. 'PZA-1A2B3C'.

  Returns:
    Dict with stored=True, the status, a human description, and minutes
    remaining, or error=True if the order number is empty.
  """
  key = str(order_number).strip().upper()
  if not key:
    return {"error": True, "error_code": "missing_order_number"}

  digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
  stage, description, minutes = _STAGES[int(digest, 16) % len(_STAGES)]
  return {
      "stored": True,
      "order_number": key,
      "status": stage,
      "description": description,
      "minutes_remaining": minutes,
  }
