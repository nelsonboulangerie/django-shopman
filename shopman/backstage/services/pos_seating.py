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


def link_tab_to_spot(*, channel_ref: str, session_key: str, seating_spot_ref: str, operator_username: str):
    spot_ref = str(seating_spot_ref or "").strip()
    label = ""
    if spot_ref:
        spot = SeatingSpot.objects.filter(ref=spot_ref).first()
        if spot is None or not spot.existed_on(seating_service.today()):
            raise PosIntentError(
                code="seating_spot_not_found",
                message="Essa mesa não está no salão de hoje.",
                field="seating_spot_ref",
                focus="cart",
            )
        label = spot.label
    return pos_service.set_pos_tab_seating(
        channel_ref=channel_ref,
        session_key=session_key,
        seating_spot_ref=spot_ref,
        operator_username=operator_username,
        spot_label=label,
    )
