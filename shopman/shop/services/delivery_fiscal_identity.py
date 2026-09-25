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


def address_gap_message(gaps: list[RecipientGap]) -> str:
    words = [_ADDRESS_WORDS.get(gap.label, gap.label) for gap in gaps if gap.field == ADDRESS_FIELD]
    return f"Para a nota fiscal da entrega, falta no endereço: {_join(words)}."


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
