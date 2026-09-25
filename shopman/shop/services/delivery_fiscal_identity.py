"""Entrega a domicílio com NFC-e: o CPF/CNPJ e o endereço completo entram na PORTA.

A SEFAZ recusa a nota de entrega a domicílio sem a identificação do consumidor e
sem o endereço completo (rejeições 787/788). Antes desta regra o pedido entrava
sem nada disso e a recusa só aparecia na emissão, com o entregador já na rua
(alerta crítico ``fiscal_emit_failed``). Decisão do dono (24/09/2026): pedir o
CPF na ENTRADA do pedido; quem não quiser informar não tem entrega, e a
retirada continua aberta.

Uma régua só, em três leitores:

- ``recipient_gaps`` é a validação que a emissão aplica. O adapter Focus
  (``fiscal_focusnfe._home_delivery_fields``) a chama para montar a própria
  recusa, e a porta do pedido a chama para recusar antes. Duas cópias
  divergiriam na primeira mudança de uma delas.
- ``requires_delivery_fiscal_identity`` pergunta "esta entrega vai ter nota?"
  ao MESMO ``emission_expected`` que decide a emissão (resolver da env). A
  exigência só vale quando a nota vai sair.
- ``DeliveryFiscalIdentityRule`` (``shop/rules/validation.py``) é a trava do
  commit: vale para todo canal que fecha pedido pelo ``CommitService``
  (loja, PDV, concierge do WhatsApp). O iFood cria o pedido pela ingestão, sem
  commit de sessão, e fica de fora por construção: lá o checkout é do iFood.

A ordem da trava importa: o que vale é a nota que VAI sair. Um CPF informado
(mesmo errado) já é pedido de nota (``on_request_or_tax_id``), então CPF
inválido é sempre recusado; sem CPF, a regra da env decide se a nota sai por
outro motivo (pagamento eletrônico, liquidação na entrega).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

#: Campo do payload das superfícies onde o CPF/CNPJ PEDIDO para a nota chega.
#: Mesmo nome no PDV e na loja; na sessão/pedido ele mora em ``fiscal.tax_id``.
TAX_ID_FIELD = "fiscal_tax_id"
ADDRESS_FIELD = "delivery_address"

#: Os códigos com que a porta recusa; quem traduz erro em campo lê daqui.
REFUSAL_CODES = frozenset({
    "delivery_tax_id_required", "delivery_tax_id_invalid", "delivery_address_incomplete",
})

_VALID_STATES = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
})


@dataclass(frozen=True)
class RecipientGap:
    """Uma lacuna do destinatário da nota de entrega.

    ``field`` é o campo da superfície onde o conserto acontece; ``label`` é o
    nome do dado que falta, na língua da casa (a emissão monta a sua recusa com
    ele); ``code`` é a chave estável do erro.
    """

    field: str
    code: str
    label: str


def _digits(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def recipient_gaps(*, tax_id, address) -> list[RecipientGap]:
    """O que falta ao destinatário para a nota de entrega a domicílio sair.

    ``tax_id`` é o documento PEDIDO para esta nota (``fiscal.tax_id``), nunca o
    do cadastro. ``address`` é o endereço estruturado da entrega
    (``delivery_address_structured``). Lista vazia = a SEFAZ tem o que pede.
    """
    from shopman.utils.documents import is_valid_tax_id

    gaps: list[RecipientGap] = []
    digits = _digits(tax_id)
    if not digits:
        gaps.append(RecipientGap(TAX_ID_FIELD, "delivery_tax_id_required", "CPF/CNPJ solicitado para a nota"))
    elif not is_valid_tax_id(digits):
        gaps.append(RecipientGap(TAX_ID_FIELD, "delivery_tax_id_invalid", "CPF/CNPJ solicitado para a nota"))

    address = address if isinstance(address, dict) else {}
    checks = (
        ("logradouro", str(address.get("route") or "").strip()),
        ("número (ou S/N explicitamente informado)", str(address.get("street_number") or "").strip()),
        ("bairro", str(address.get("neighborhood") or "").strip()),
        ("município", str(address.get("city") or "").strip()),
        ("UF válida", str(address.get("state_code") or "").strip().upper() in _VALID_STATES),
        ("CEP de 8 dígitos", len(_digits(address.get("postal_code"))) == 8),
    )
    for label, ok in checks:
        if not ok:
            gaps.append(RecipientGap(ADDRESS_FIELD, "delivery_address_incomplete", label))
    return gaps


# ── A exigência ──────────────────────────────────────────────────────────

#: Como cada lacuna de endereço aparece para quem CONSERTA (cliente ou
#: operador). O rótulo da emissão ("UF válida", "CEP de 8 dígitos") é jargão de
#: validação; na porta do pedido a frase diz o que escrever.
_ADDRESS_WORDS = {
    "logradouro": "a rua",
    "número (ou S/N explicitamente informado)": "o número (ou S/N)",
    "bairro": "o bairro",
    "município": "a cidade",
    "UF válida": "o estado",
    "CEP de 8 dígitos": "o CEP",
}

TAX_ID_REQUIRED_MESSAGE = "Para entregar, precisamos do CPF ou CNPJ para a nota fiscal."
TAX_ID_INVALID_MESSAGE = "Confira o CPF ou CNPJ: os números não conferem."


def _join(words: list[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " e " + words[-1]


def address_gap_words(gaps: list[RecipientGap]) -> list[str]:
    """As lacunas de endereço como quem CONSERTA lê ("o número (ou S/N)", "o CEP")."""
    return [_ADDRESS_WORDS.get(gap.label, gap.label) for gap in gaps if gap.field == ADDRESS_FIELD]


def join_words(words: list[str]) -> str:
    """``["a rua", "o CEP"]`` → ``"a rua e o CEP"``."""
    return _join(words)


def address_gap_message(gaps: list[RecipientGap]) -> str:
    return f"Para a nota fiscal da entrega, falta no endereço: {_join(address_gap_words(gaps))}."


def order_view(*, data: dict, channel_ref: str = "", total_q: int = 0, ref: str = ""):
    """O pedido que AINDA não existe, na forma que o resolver fiscal lê.

    Os resolvers (``fiscal_resolvers``) leem ``data``, ``channel_ref`` e
    ``total_q``. Antes do commit, ``data`` é o ``session.data`` (o commit copia
    para o pedido as mesmas chaves que eles consultam: ``fiscal``, ``receipt``,
    ``payment``, ``fulfillment_type``).
    """
    return SimpleNamespace(
        ref=ref, channel_ref=channel_ref, total_q=int(total_q or 0), data=dict(data or {}),
        status="new", pk=None,
    )


def requires_delivery_fiscal_identity(order) -> bool:
    """Esta entrega a domicílio vai ter NFC-e?

    Mesma pergunta, mesma resposta que a emissão: ``fiscal.emission_expected``
    (backend fiscal configurado + resolver da env). Retirada nunca exige.
    """
    data = getattr(order, "data", None) or {}
    if data.get("fulfillment_type") != "delivery":
        return False
    from shopman.shop.services import fiscal

    return fiscal.emission_expected(order)


def delivery_fiscal_gaps(order) -> list[RecipientGap]:
    """As lacunas que impedem esta entrega de entrar — vazio quando pode.

    Sem nota prevista, nada falta. Com nota, a régua é a da emissão.
    """
    if not requires_delivery_fiscal_identity(order):
        return []
    data = getattr(order, "data", None) or {}
    return recipient_gaps(
        tax_id=(data.get("fiscal") or {}).get("tax_id"),
        address=data.get("delivery_address_structured"),
    )


def refusal(gaps: list[RecipientGap]) -> tuple[str, str, str] | None:
    """``(code, field, message)`` da recusa, ou ``None``. O CPF vem primeiro.

    Uma recusa por vez, no campo que o conserto pede: com o CPF faltando e o
    endereço incompleto, o CPF é o que só a pessoa pode dar.
    """
    if not gaps:
        return None
    tax = next((gap for gap in gaps if gap.field == TAX_ID_FIELD), None)
    if tax is not None:
        message = TAX_ID_REQUIRED_MESSAGE if tax.code == "delivery_tax_id_required" else TAX_ID_INVALID_MESSAGE
        return tax.code, TAX_ID_FIELD, message
    return "delivery_address_incomplete", ADDRESS_FIELD, address_gap_message(gaps)


def delivery_tax_id_required_for_methods(*, channel_ref: str, methods) -> bool:
    """A entrega deste canal pede CPF, com a forma de pagamento que for?

    A tela da loja precisa saber ANTES de o cliente escolher o pagamento (o
    endereço vem primeiro). A pergunta é feita ao mesmo resolver, uma vez por
    forma de pagamento oferecida, sem CPF: se QUALQUER uma leva a nota, o CPF é
    pedido na entrega. Pedir a mais numa env em que uma forma não emite custa um
    campo; pedir a menos custa o pedido recusado no fim.
    """
    for method in methods or ():
        payment = {"method": method}
        if method == "cash":
            payment["collection"] = "on_delivery"
        probe = order_view(
            data={"fulfillment_type": "delivery", "payment": payment},
            channel_ref=channel_ref,
        )
        if requires_delivery_fiscal_identity(probe):
            return True
    return False


# ── Guardar para as próximas entregas (só quando PERGUNTADO) ─────────────

SAVED = "saved"
KEPT_EXISTING = "kept_existing"
OWNED_BY_OTHER = "owned_by_other"
NOT_SAVED = "not_saved"


def saved_tax_id(customer_uuid) -> str:
    """O CPF/CNPJ do cadastro, para PRÉ-PREENCHER a nota da próxima entrega.

    Pré-preencher não é pedir: o campo aparece preenchido e a pessoa confirma
    (ou troca, para a nota sair no documento de outra pessoa) no mesmo passo.
    """
    if not customer_uuid:
        return ""
    from shopman.guestman.services import customer as customer_service

    customer = customer_service.get_by_uuid(str(customer_uuid))
    return _digits(getattr(customer, "document", "")) if customer is not None else ""


def save_tax_id_to_customer(customer_uuid, tax_id) -> str:
    """Guarda o CPF/CNPJ da nota no cadastro, quando a pessoa DISSE que quer.

    Só preenche lacuna: o documento do cadastro nunca é trocado daqui (CPF não
    muda na vida de ninguém; um CPF diferente é quase sempre a nota de outra
    pessoa, e trocar identidade fiscal é gesto com atrito, do PDV). Documento
    que já é de outro cadastro também não entra. Nos dois casos a nota do
    pedido sai com o CPF informado; só o cadastro fica como estava.
    """
    from shopman.utils.documents import is_valid_tax_id

    digits = _digits(tax_id)
    if not customer_uuid or not is_valid_tax_id(digits):
        return NOT_SAVED
    from django.db import transaction
    from shopman.guestman.models import Customer
    from shopman.guestman.services import customer as customer_service

    with transaction.atomic():
        customer = Customer.objects.select_for_update().filter(uuid=str(customer_uuid), is_active=True).first()
        if customer is None:
            return NOT_SAVED
        if _digits(customer.document):
            return KEPT_EXISTING
        if Customer.objects.filter(document=digits).exclude(pk=customer.pk).exists():
            return OWNED_BY_OTHER
        customer_service.update(customer.ref, document=digits)
    return SAVED
