"""A posição do entregador como o Gestor mostra: onde, de quando e por quem (F7b).

Só lê (``courier_position.read``): a tela nunca pergunta ao serviço nem grava nada.
A idade ("Posição agora", "Última posição há 3 min") é conta da tela, que tem o
relógio andando; aqui sai a hora da posição.
"""

from __future__ import annotations

from dataclasses import dataclass

from shopman.shop.services import courier_position

#: Quem disse onde o entregador está, completando "Posição agora, …".
_SOURCE_LABELS = {
    courier_position.SOURCE_WEBHOOK: "pela TaOn",
    courier_position.SOURCE_POLL: "pela TaOn",
    courier_position.SOURCE_OWN_FLEET: "pelo celular do entregador",
}


@dataclass(frozen=True)
class DeliveryCourierPositionProjection:
    """Onde o entregador estava na última posição recebida."""

    latitude: float
    longitude: float
    #: A hora da posição (ISO com fuso), não a da chegada aqui.
    at: str
    #: "pela TaOn" ou "pelo celular do entregador".
    source_label: str


def courier_position_projection(ride_ref) -> DeliveryCourierPositionProjection | None:
    position = courier_position.read(ride_ref)
    if position is None:
        return None
    return DeliveryCourierPositionProjection(
        latitude=position["latitude"],
        longitude=position["longitude"],
        at=position["at"].isoformat(),
        source_label=_SOURCE_LABELS[position["source"]],
    )
