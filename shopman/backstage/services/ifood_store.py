"""Os dois gestos da tela "A loja no iFood" que escrevem no iFood.

A leitura mora em ``backstage/projections/ifood_merchant_console.py``; o que grava
mora aqui, para a projeção nunca escrever (ADR-014 §4.2). Os dois gestos não são
conceito novo: gravar o horário é o mesmo ``sync_store`` que salvar o horário da
casa no Admin dispara pela fila; remover pausa só vale para a pausa feita fora do
Gestor (Portal do Parceiro).
"""

from __future__ import annotations

from datetime import datetime

from shopman.shop.services import ifood_merchant


class PauseNotRemovable(Exception):
    """A pausa é do Gestor ou do calendário: removê-la direto voltaria na próxima gravação."""


def remove_portal_interruption(interruption_id: str) -> None:
    """Remove no iFood uma pausa feita fora do Gestor (Portal do Parceiro).

    A pausa do Gestor sai ligando o iFood de novo (toggle do canal) e a do calendário sai
    pelo calendário: apagar qualquer uma delas aqui seria desfeito pela próxima
    gravação, e o gestor veria a pausa "voltar sozinha".
    """
    from shopman.shop.models import IFoodInterruption

    ours = IFoodInterruption.objects.filter(merchant_id=ifood_merchant.merchant_id(), ifood_id=interruption_id).exists()
    if ours:
        raise PauseNotRemovable(interruption_id)
    ifood_merchant.delete_interruption(interruption_id)


def write_opening_hours(*, now: datetime | None = None) -> None:
    """Grava agora no iFood o horário da casa (o mesmo ``sync_store`` da fila).

    Levanta ``MerchantAPIError`` com a recusa do iFood (400 de turno sobreposto, 403).
    """
    result = ifood_merchant.sync_store(now=now)
    if result.hours_error is not None:
        # O ``sync_store`` engole a recusa do horário para a pausa não depender dele
        # (DEV-2026-041); quem pediu para gravar o horário precisa ouvir a recusa.
        raise result.hours_error


__all__ = ["PauseNotRemovable", "remove_portal_interruption", "write_opening_hours"]
