"""Venda por intermediador: o que é dinheiro da casa, e quem intermediou.

Uma venda por plataforma de terceiro tem **dois donos de dinheiro dentro do
mesmo total**. O ``orderAmount`` do iFood é, pela composição oficial deles,
``subTotal + deliveryFee + additionalFees − benefits``, e a própria plataforma
diz das ``additionalFees`` que "todas representam receita do iFood e não devem
ser adicionadas à nota fiscal". A nota da casa declara a venda da casa — quem
emite é o estabelecimento, o intermediador só intermedeia.

Além do valor, a nota precisa **dizer que houve intermediação**: o Ajuste
SINIEF 22/20 (CONFAZ, efeitos desde abr/2021) pede o ``indIntermed`` e o grupo
``infIntermed`` (CNPJ do intermediador + identificador do cadastro da loja na
plataforma).

**Este módulo é sobre INTERMEDIADOR, não sobre iFood.** O conceito é da nota e
vale para qualquer marketplace; por isso a camada fiscal não ganha nenhum
``if channel == "ifood"``. O que é por plataforma é só a *leitura* do
detalhamento financeiro, porque cada uma entrega o dela com um nome próprio —
e hoje existe uma só, lida aqui pelo nome dela, sem registry plugável para um
segundo consumidor que não existe.

Quem é intermediador não é palpite do código: é a configuração
``settings.SHOPMAN_FISCAL_INTERMEDIARIES`` (canal → CNPJ/identificador), porque
o CNPJ do intermediador é dado do deployment, não do pedido.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

#: O único valor de ``deliveredBy`` que põe a taxa de entrega NA NOTA.
#:
#: A regra fiscal é sobre quem prestou o transporte: entrega da **loja** ⇒ a
#: taxa é receita da loja e consta na nota; entrega da **plataforma** ⇒ não
#: consta, porque nem o serviço nem o dinheiro são da casa. Hoje, na Nelson,
#: todo pedido do iFood é entregue pelo iFood — mas a regra é lida do campo, e
#: não cravada, justamente para que o dia em que a entrega própria for ligada a
#: nota saia certa em vez de errada em silêncio.
MERCHANT_DELIVERY = "MERCHANT"


def _configured(channel_ref: str) -> dict:
    mapping = dict(getattr(settings, "SHOPMAN_FISCAL_INTERMEDIARIES", {}) or {})
    entry = mapping.get(str(channel_ref or ""))
    return dict(entry) if isinstance(entry, dict) else {}


def _digits(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def is_intermediated(order) -> bool:
    """Esta venda veio por plataforma de terceiro?

    A pergunta é do canal, não do conteúdo do pedido: quem declara que um canal
    é marketplace é o deployment.
    """
    return bool(_configured(getattr(order, "channel_ref", "")))


def intermediary_for(order) -> dict | None:
    """Grupo do intermediador desta venda, ou ``None``.

    ``None`` cobre dois casos diferentes de propósito, e ambos significam "não
    mande o grupo": a casa vendeu direto (canal não intermediado), ou o canal é
    intermediado e **falta configuração** para preencher o grupo.

    Os dois campos são obrigatórios juntos — a Focus NF-e documenta
    ``cnpj_intermediario`` e ``id_intermediario`` como obrigatórios quando
    ``indicador_intermediario = 1``. Meio grupo não é meio-certo: é nota
    recusada. Sem o identificador do cadastro da loja na plataforma (que é
    pergunta em aberto para o contador), o grupo não sai — e a ausência
    **grita**, em :func:`missing_configuration`, em vez de virar uma nota
    silenciosamente fora do Ajuste SINIEF 22/20.
    """
    entry = _configured(getattr(order, "channel_ref", ""))
    if not entry:
        return None
    cnpj = _digits(entry.get("cnpj"))
    id_cad = str(entry.get("id_cad_int_tran") or "").strip()
    if len(cnpj) != 14 or len(id_cad) < 2:
        return None
    return {"cnpj": cnpj, "id_cad_int_tran": id_cad[:60]}


def missing_configuration(order) -> str:
    """Por que o grupo do intermediador não pode ser montado nesta venda.

    ``""`` quando não há nada faltando (inclusive quando a venda não é
    intermediada). Texto para humano quando falta — é o que o alerta do
    operador mostra.
    """
    entry = _configured(getattr(order, "channel_ref", ""))
    if not entry:
        return ""
    missing = []
    if len(_digits(entry.get("cnpj"))) != 14:
        missing.append("CNPJ do intermediador (14 dígitos)")
    if len(str(entry.get("id_cad_int_tran") or "").strip()) < 2:
        missing.append("identificador do cadastro da loja na plataforma (idCadIntTran, 2 a 60 caracteres)")
    return ", ".join(missing)


def seller_amounts(order) -> dict | None:
    """A base da nota desta venda intermediada: ``{"base_q", "freight_q"}``.

    ``None`` = **nada a corrigir**, e a nota segue pelo total do pedido como
    sempre: ou o canal não é intermediado, ou a plataforma não mandou o
    detalhamento financeiro (pedido de simulação, payload antigo). Um canal
    intermediado sem detalhamento não é motivo para inventar número.

    ``base_q`` é o que a nota declara: o total do pedido **menos** a receita da
    plataforma, e menos a taxa de entrega quando quem entregou foi a
    plataforma. ``freight_q`` é a taxa que sobra para a nota — zero quando não
    é da casa.

    ⚠️ ``Order.total_q`` continua sendo o total do PEDIDO (o que o cliente
    pagou ao iFood), e nada aqui o altera: B.I., fechamento e telas leem o
    total do pedido e ele não mudou de significado. O que muda é só a base
    **da nota**.
    """
    if not is_intermediated(order):
        return None

    totals = (((order.data or {}).get("ifood") or {}).get("totals") or {})
    order_amount_q = int(totals.get("order_amount_q") or 0)
    if order_amount_q <= 0:
        return None

    additional_fees_q = max(0, int(totals.get("additional_fees_q") or 0))
    delivery_fee_q = max(0, int(totals.get("delivery_fee_q") or 0))
    delivered_by = str(((order.data or {}).get("ifood") or {}).get("delivered_by") or "").strip().upper()

    freight_q = delivery_fee_q if delivered_by == MERCHANT_DELIVERY else 0
    # O que sai da base: a receita da plataforma, sempre; e a taxa de entrega
    # quando o transporte não foi da casa. Os ``benefits`` continuam onde já
    # estavam — dentro do ``orderAmount``, portanto reduzindo a base, que é a
    # leitura de cupom patrocinado pela LOJA. Cupom patrocinado pelo iFood tem
    # outra leitura (repasse, ou seja, pagamento) e muda a base tributável:
    # decisão do contador, não deste módulo. Ver a pergunta aberta no PR.
    base_q = order_amount_q - additional_fees_q - (delivery_fee_q - freight_q)
    return {"base_q": base_q, "freight_q": freight_q}


__all__ = [
    "MERCHANT_DELIVERY",
    "intermediary_for",
    "is_intermediated",
    "missing_configuration",
    "seller_amounts",
]
