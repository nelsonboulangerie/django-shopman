"""O CPF/CNPJ que já vem preenchido na nota da próxima entrega.

A regra de exigência mora em ``shop/services/delivery_fiscal_identity`` (a mesma
da trava do commit e da emissão). Aqui fica só o lado de LEITURA que a tela
consome: que documento a casa já conhece para pré-preencher o campo.

Decisão do dono (25/09/2026): entrega pede CPF sempre, então perguntar "guardar
para as próximas entregas?" era ruído. Na próxima entrega o CPF vem preenchido
e vale (editável), sem pergunta e sem gravar nada. A ordem da procura:

1. ``customer.document`` — o documento do cadastro, quando existe;
2. senão, o ``fiscal.tax_id`` do último pedido de ENTREGA do mesmo cliente.

O segundo é LIDO do pedido e devolvido só para a própria pessoa, no campo dela;
nunca vira ``customer.document`` (pode ser o CPF do marido, o da empresa — ver
``fiscal`` em ``docs/reference/data-schemas.md``).
"""

from __future__ import annotations

from dataclasses import dataclass

#: De onde veio o documento pré-preenchido; a tela diz isso ao lado do campo.
FROM_DOCUMENT = "document"
FROM_LAST_DELIVERY = "last_delivery"


@dataclass(frozen=True)
class DeliveryTaxIdPrefill:
    """``tax_id``: só dígitos, vazio quando a casa não conhece nenhum.
    ``source``: ``FROM_DOCUMENT``, ``FROM_LAST_DELIVERY`` ou vazio."""

    tax_id: str = ""
    source: str = ""


def _digits(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def delivery_tax_id_prefill(customer_uuid) -> DeliveryTaxIdPrefill:
    if not customer_uuid:
        return DeliveryTaxIdPrefill()
    from shopman.guestman.services import customer as customer_service

    customer = customer_service.get_by_uuid(str(customer_uuid))
    if customer is None:
        return DeliveryTaxIdPrefill()
    document = _digits(customer.document)
    if document:
        return DeliveryTaxIdPrefill(tax_id=document, source=FROM_DOCUMENT)

    from shopman.orderman.models import Order
    from shopman.utils.documents import is_valid_tax_id

    last_fiscal = (
        Order.objects.filter(
            data__customer_ref=customer.ref,
            data__fulfillment_type="delivery",
            data__fiscal__has_key="tax_id",
        )
        .exclude(data__fiscal__tax_id="")
        .order_by("-created_at", "-id")
        .values_list("data__fiscal", flat=True)
        .first()
    )
    tax_id = _digits((last_fiscal or {}).get("tax_id")) if isinstance(last_fiscal, dict) else ""
    if tax_id and is_valid_tax_id(tax_id):
        return DeliveryTaxIdPrefill(tax_id=tax_id, source=FROM_LAST_DELIVERY)
    return DeliveryTaxIdPrefill()
