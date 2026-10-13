"""Vínculo OPCIONAL comanda × mesa, do lado do backstage (dono das mesas).

Confere que a mesa existe no salão de hoje (``SeatingSpot`` vigente) e entrega ao
serviço do PDV no shop (``shop/services/pos.set_pos_tab_seating``), que guarda o
vínculo na comanda. O shop não lê o cadastro do backstage; quem conhece a mesa é
este lado.
"""

from __future__ import annotations

from shopman.backstage.models import SeatingSpot
from shopman.backstage.services import seating as seating_service
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError


def spot_label_today(seating_spot_ref: str) -> str:
    """O nome da mesa do salão de HOJE, ou a recusa (a mesa não existe ou saiu do salão)."""
    spot = SeatingSpot.objects.filter(ref=str(seating_spot_ref or "").strip()).first()
    if spot is None or not spot.existed_on(seating_service.today()):
        raise PosIntentError(
            code="seating_spot_not_found",
            message="Essa mesa não está no salão de hoje.",
            field="seating_spot_ref",
            focus="cart",
        )
    return spot.label


def link_tab_to_spot(*, channel_ref: str, session_key: str, seating_spot_ref: str, operator_username: str):
    spot_ref = str(seating_spot_ref or "").strip()
    label = spot_label_today(spot_ref) if spot_ref else ""
    return pos_service.set_pos_tab_seating(
        channel_ref=channel_ref,
        session_key=session_key,
        seating_spot_ref=spot_ref,
        operator_username=operator_username,
        spot_label=label,
    )
