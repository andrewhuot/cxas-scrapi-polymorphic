"""Quote the price of one pizza.

Pure helper the Order Agent calls to give the customer an accurate price
before placing the order. Prices match the get_menu tool.
"""

from typing import Any


_SIZE_PRICES = {"small": 9.0, "medium": 12.0, "large": 15.0}
_TOPPING_PRICE = 1.5


def _parse_toppings(toppings: str) -> list[str]:
  return [t.strip() for t in str(toppings).split(",") if t.strip()]


def quote_pizza(size: str, toppings: str = "") -> dict[str, Any]:
  """Calculate the price of a single pizza.

  Args:
    size: 'small', 'medium', or 'large'.
    toppings: Comma-separated topping names (may be empty).

  Returns:
    Dict with stored=True and a price breakdown, or error=True if the size
    is not on the menu.
  """
  size = str(size).lower().strip()
  if size not in _SIZE_PRICES:
    return {"error": True, "error_code": "invalid_size"}

  topping_list = _parse_toppings(toppings)
  base = _SIZE_PRICES[size]
  toppings_total = round(len(topping_list) * _TOPPING_PRICE, 2)
  total = round(base + toppings_total, 2)
  return {
      "stored": True,
      "size": size,
      "toppings": topping_list,
      "base_price": base,
      "toppings_total": toppings_total,
      "total": total,
      "currency": "USD",
  }
