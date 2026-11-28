"""POS adapter — wraps Backstage POS tab persistence with lazy imports."""

from __future__ import annotations


def upsert_tab(*, ref: str, label: str, display: str) -> dict:
    from shopman.backstage.models import POSTab

    tab, _ = POSTab.objects.update_or_create(
        ref=ref,
        defaults={
            "label": label or display,
            "is_active": True,
        },
    )
    return {"tab_ref": tab.ref, "tab_display": tab.display_ref}


def ensure_tab(*, ref: str, display: str) -> str:
    from shopman.backstage.models import POSTab

    tab, _ = POSTab.objects.get_or_create(ref=ref, defaults={"label": display})
    return tab.display_ref


def active_tab_refs() -> list[str]:
    """As referências das comandas cadastradas e ativas (o quadro do PDV)."""
    from shopman.backstage.models import POSTab

    return list(POSTab.objects.filter(is_active=True).values_list("ref", flat=True))
