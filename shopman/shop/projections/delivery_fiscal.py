"""Leitura da exigência fiscal da entrega, para as superfícies.

A regra mora em ``shop/services/delivery_fiscal_identity`` (a mesma da trava do
commit e da emissão). Aqui fica só o lado de LEITURA que a tela consome: a
entrega deste canal pede CPF? que CPF o cadastro já tem para pré-preencher?
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryTaxIdContext:
    """``required``: a entrega vai com nota e a nota não sai sem CPF/CNPJ.
    ``saved_tax_id``: o documento do cadastro (vazio quando não há, ou quando a
    sessão não pode vê-lo). ``offer_save``: a tela pode PERGUNTAR se guarda."""

    required: bool = False
    saved_tax_id: str = ""
    offer_save: bool = False


def delivery_tax_id_context(*, channel_ref: str, methods, customer_uuid=None) -> DeliveryTaxIdContext:
    from shopman.shop.services import delivery_fiscal_identity as identity

    required = identity.delivery_tax_id_required_for_methods(channel_ref=channel_ref, methods=methods)
    if not customer_uuid:
        return DeliveryTaxIdContext(required=required)
    saved = identity.saved_tax_id(customer_uuid)
    return DeliveryTaxIdContext(required=required, saved_tax_id=saved, offer_save=not saved)
