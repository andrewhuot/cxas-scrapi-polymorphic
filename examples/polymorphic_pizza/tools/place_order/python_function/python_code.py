"""Place a confirmed pizza order.

Stateless: the whole order is passed in one call. Returns a deterministic
order number (derived from the order details) plus the total and an ETA, so
the demo behaves the same on every run without any backend.
"""

import hashlib
from typing import Any


_SIZE_PRICES = {"small": 9.0, "medium": 12.0, "large": 15.0}
_TOPPING_PRICE = 1.5
_DELIVERY_FEE = 4.0
_VALID_FULFILLMENT = {"pickup", "delivery"}


def _parse_toppings(toppings: str) -> list[str]:
  return [t.strip() for t in str(toppings).split(",") if t.strip()]


def _order_number(seed: str) -> str:
  digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
  return "PZA-" + digest[:6].upper()


def place_order(
    size: str,
    toppings: str,
    fulfillment: str,
    customer_name: str,
    address: str = "",
) -> dict[str, Any]:
  """Place a confirmed pizza order.

  Args:
    size: 'small', 'medium', or 'large'.
    toppings: Comma-separated topping names (may be empty).
    fulfillment: 'pickup' or 'delivery'.
    customer_name: Name the order is under.
    address: Delivery address; required when fulfillment is 'delivery'.

  Returns:
    Dict with stored=True, an order_number, the total, and an ETA in
    minutes, or error=True with an error_code on invalid input.
  """
  size = str(size).lower().strip()
  fulfillment = str(fulfillment).lower().strip()
  name = str(customer_name).strip()

  if size not in _SIZE_PRICES:
    return {"error": True, "error_code": "invalid_size"}
  if fulfillment not in _VALID_FULFILLMENT:
    return {"error": True, "error_code": "invalid_fulfillment"}
  if not name:
    return {"error": True, "error_code": "missing_name"}
  if fulfillment == "delivery" and not str(address).strip():
    return {"error": True, "error_code": "missing_address"}

  topping_list = _parse_toppings(toppings)
  subtotal = _SIZE_PRICES[size] + len(topping_list) * _TOPPING_PRICE
  delivery_fee = _DELIVERY_FEE if fulfillment == "delivery" else 0.0
  total = round(subtotal + delivery_fee, 2)
  eta = 40 if fulfillment == "delivery" else 20

  seed = f"{name}|{size}|{','.join(topping_list)}|{fulfillment}|{address}"
  return {
      "stored": True,
      "order_number": _order_number(seed),
      "size": size,
      "toppings": topping_list,
      "fulfillment": fulfillment,
      "customer_name": name,
      "delivery_fee": delivery_fee,
      "total": total,
      "currency": "USD",
      "eta_minutes": eta,
  }
