"""Render a structured order confirmation card for the chat channel.

Chat-only tool added by the polymorphism engine. Builds a JSON payload that
the web chat widget renders as a card (title, summary, total, action
buttons) instead of plain text.
"""

from typing import Any


def send_order_card(
    title: str,
    summary: str = "",
    total: str = "",
    buttons: str = "",
) -> dict[str, Any]:
  """Build an order confirmation card payload.

  Args:
    title: Card heading, e.g. "Order Confirmed".
    summary: Short order summary shown under the title.
    total: The order total as text, e.g. "$18.00".
    buttons: Comma-separated action button labels (e.g. "Confirm,Edit").

  Returns:
    Dict with stored=True and a 'card' payload, or error=True if no title.
  """
  if not title:
    return {"error": True, "error_code": "missing_title"}

  labels = [b.strip() for b in buttons.split(",") if b.strip()]
  card = {
      "type": "order_card",
      "title": title,
      "summary": summary,
      "total": total,
      "buttons": [
          {"label": label, "action": label.lower()} for label in labels
      ],
  }
  return {"stored": True, "card": card}
