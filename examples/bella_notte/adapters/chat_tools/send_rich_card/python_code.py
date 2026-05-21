"""Render a structured rich card for the chat channel.

Chat-only tool added by the polymorphism engine. Constructs a JSON payload
representing a confirmation card (title, body, action buttons) that the web
chat widget renders visually instead of plain text.
"""

from typing import Any


def send_rich_card(
    title: str,
    body: str = "",
    buttons: str = "",
) -> dict[str, Any]:
  """Build a rich card payload for the chat widget.

  Args:
    title: Card heading, e.g. "Reservation Confirmed".
    body: Short summary text shown under the title.
    buttons: Comma-separated action button labels (e.g. "Confirm,Change").

  Returns:
    Dict with stored=True and a 'card' payload on success, or error=True on
    failure.
  """
  if not title:
    return {"error": True, "error_code": "missing_title"}

  labels = [b.strip() for b in buttons.split(",") if b.strip()]
  card = {
      "type": "rich_card",
      "title": title,
      "body": body,
      "buttons": [
          {"label": label, "action": label.lower()} for label in labels
      ],
  }
  return {"stored": True, "card": card}
