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
#: Triagem da primeira rodada da ponte (21/11/2026): os quatro do público "operations"
#: abaixo não têm gesto de balcão; quem resolve muda código ou integração.
#: ``stock_hold_gap`` fica com a Operação: é venda consumada acima do estoque contado,
#: e o gesto é contar o estoque.
OWNER_OVERRIDES = {
    "lifecycle_phase_stuck": ENGINEERING,
    "ifood_store_sync_failed": ENGINEERING,
    # Evento do iFood sem tratador: falta o tratador no código.
    "ifood_event_unhandled": ENGINEERING,
    # Reserva que sobrou sem dono, devolvida pela varredura: vazamento no código.
    "orphan_holds_released": ENGINEERING,
    # O aviso "voltou ao estoque" ao cliente: entrega da fila de envio.
    "stock_alert_dispatch_unknown": ENGINEERING,
    "stock_alert_delivery_stuck": ENGINEERING,
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
