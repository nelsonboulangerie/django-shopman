"""Quem responde por cada tipo de alerta, e onde o gesto mora.

Sem tabela de 150 linhas: o dono sai do público do alerta (o mesmo recorte que
decide quem vê no sino), e os avisos de sistema são da Engenharia. Exceção
nominal só quando o público engana.
"""

from __future__ import annotations

ENGINEERING = "Engenharia"

OWNER_BY_AUDIENCE = {
    "orders": "Gestor de pedidos",
    "production": "Produção",
    "finance": "Financeiro",
    "operations": "Operação",
}

#: Tipos cujo dono não é o do público: a causa está no código ou na integração.
OWNER_OVERRIDES = {
    "lifecycle_phase_stuck": ENGINEERING,
    "ifood_store_sync_failed": ENGINEERING,
}


def owner_for(alert_type: str, *, audience: str = "") -> str:
    from shopman.backstage.services.alerts import SYSTEM_TYPES

    if alert_type in OWNER_OVERRIDES:
        return OWNER_OVERRIDES[alert_type]
    if alert_type in SYSTEM_TYPES:
        return ENGINEERING
    return OWNER_BY_AUDIENCE.get(audience, ENGINEERING)


def home_for(alert_type: str) -> str:
    """O botão do aviso, em texto: app, caminho e rótulo. Vazio quando é Admin ou fora."""

    from shopman.backstage.projections.alerts import alert_home

    home = alert_home(alert_type)
    if home is None:
        return ""
    surface, path, label = home
    return f"{label} ({surface} {path})"
