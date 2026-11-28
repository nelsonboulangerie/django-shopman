"""Shopman Utils — shared primitives and admin helpers for the Shopman suite."""

from shopman.utils.contrib.admin_unfold.badges import unfold_badge, unfold_badge_numeric
from shopman.utils.contrib.admin_unfold.render import unfold_component, unfold_link
from shopman.utils.contrib.admin_unfold.tables import table_badge

__version__ = "0.3.0"

__all__ = [
    "MoneyReaisField",
    "parse_reais",
    "table_badge",
    "unfold_badge",
    "unfold_badge_numeric",
    "unfold_component",
    "unfold_link",
]


def __getattr__(name: str):
    # O campo de reais importa os widgets do Unfold, que leem as settings do
    # Django: exportar sob demanda mantém ``import shopman.utils`` barato e
    # seguro antes do ``django.setup()``.
    if name in {"MoneyReaisField", "parse_reais"}:
        from shopman.utils.contrib.admin_unfold import money

        return getattr(money, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
