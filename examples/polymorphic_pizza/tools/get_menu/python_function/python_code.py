"""Return the Polymorphic Pizza menu.

Read-only tool. The prices here are the single source of truth that the
quote_pizza and place_order tools also use, so the agent never has to invent
a price.
"""

from typing import Any


_SIZE_PRICES = {"small": 9.0, "medium": 12.0, "large": 15.0}

_SPECIALTY_PIZZAS = [
    "Margherita (tomato, mozzarella, basil)",
    "Pepperoni Classic",
    "Veggie Supreme (peppers, onion, mushroom, olive)",
    "Meat Lovers (pepperoni, sausage, bacon)",
]

_TOPPINGS = [
    "pepperoni",
    "sausage",
    "bacon",
    "mushroom",
    "onion",
    "green pepper",
    "olive",
    "pineapple",
    "extra cheese",
    "spinach",
]

_TOPPING_PRICE = 1.5


def get_menu() -> dict[str, Any]:
  """Return the full menu.

  Returns:
    Dict with stored=True and a 'menu' payload of sizes, specialty pizzas,
    toppings, and the per-topping price.
  """
  return {
      "stored": True,
      "menu": {
          "sizes": _SIZE_PRICES,
          "specialty_pizzas": _SPECIALTY_PIZZAS,
          "toppings": _TOPPINGS,
          "topping_price": _TOPPING_PRICE,
          "currency": "USD",
      },
  }
