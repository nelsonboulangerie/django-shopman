"""
Shared helpers for reading canonical order data fields.

These helpers centralise fallback logic for fields that were renamed
during the session→order data schema evolution.
"""

from __future__ import annotations

import logging
from datetime import date

from django.utils import timezone

logger = logging.getLogger(__name__)


def get_fulfillment_type(order) -> str:
    """Return the order's fulfillment type.

    Uses the canonical ``fulfillment_type`` key with a fallback to the
    legacy ``delivery_method`` key so both old and new orders work.

    Returns an empty string when neither key is present.
    """
    return (
        (order.data or {}).get("fulfillment_type")
        or (order.data or {}).get("delivery_method", "")
    )


def is_test_order(order) -> bool:
    """O pedido é um pedido de TESTE de marketplace: visível e operável, inerte.

    A homologação do iFood é feita contra o ambiente VIVO: o Developer Portal
    gera pedidos que entram pelo polling como qualquer outro, e o iFood valida
    as transições do lado DELES (nossos callbacks). Por isso o pedido precisa
    aparecer no Gestor e ser aceito, despachado e concluído normalmente — o que
    ele não pode é tocar no físico e no financeiro da casa: estoque, cozinha,
    nota fiscal, aviso ao cliente e fidelidade ficam de fora.

    A marca já nasce na ingestão (``ifood_ingest`` grava
    ``data["ifood"]["is_test"]`` a partir do ``isTest`` do payload). Esta função
    é o ÚNICO lugar onde ela é lida: cada supressão pergunta aqui, e outra
    origem de teste, quando existir, ganha seu ramo nesta função e em mais
    lugar nenhum.

    Só o booleano ``True`` conta. Qualquer outro valor (ausente, ``None``, a
    string ``"false"``) significa pedido real — na dúvida, o pedido é de
    verdade e a casa trabalha.
    """
    data = getattr(order, "data", None) or {}
    ifood = data.get("ifood")
    if isinstance(ifood, dict) and ifood.get("is_test") is True:
        return True
    return False


def delivery_ownership(order) -> str:
    """De quem é a responsabilidade de levar este pedido até o cliente?

    Quatro respostas, e a pergunta por trás delas é sempre a mesma: **a
    logística é de um terceiro que já tem os dados do cliente?**

    - ``"house"`` — a casa. Inclusive quando quem pedala é transportadora
      contratada por ela (a Nelson usa Taon Delivery/Taxi Machine no canal
      próprio): quem contrata o entregador é a loja, então é a loja que precisa
      dizer a ele onde tocar a campainha. Terceirizada da casa não é terceiro
      com os dados do cliente — ela não tem app nenhum, tem o papel.
    - ``"marketplace"`` — o marketplace. O entregador chega com o endereço e o
      telefone já na tela do app dele; repetir isso no papel não ajuda ninguém
      e espalha dado pessoal.
    - ``"unknown"`` — pedido de marketplace em que o responsável não veio no
      payload. Na dúvida a casa NÃO repete dado pessoal: desconhecido não é
      autorização, é falta de prova — a mesma porta que
      ``ifood_ingest._collection_on_delivery`` fecha para a cobrança.
    - ``"none"`` — retirada. Não há entrega, logo não há dono dela.

    A marca vem de ``data["ifood"]["delivered_by"]`` (``deliveredBy`` do Order
    Module). Pedido sem bloco de marketplace é pedido do canal próprio, e no
    canal próprio a entrega é sempre compromisso da casa. Outra origem de
    marketplace, quando existir, ganha seu ramo AQUI — este é o único lugar em
    que a pergunta é respondida.
    """
    if get_fulfillment_type(order) != "delivery":
        return "none"
    data = getattr(order, "data", None) or {}
    ifood = data.get("ifood")
    if not isinstance(ifood, dict):
        return "house"
    owner = str(ifood.get("delivered_by") or "").strip().upper()
    if owner == "MERCHANT":
        return "house"
    if owner == "IFOOD":
        return "marketplace"
    return "unknown"


def house_owns_the_delivery(order) -> bool:
    """A entrega é compromisso da CASA — a logística não é de terceiro.

    Predicado de :func:`delivery_ownership`, e a razão de ele existir separado é
    que quem pergunta quase sempre quer só o sim/não.

    Retirada responde ``False``: ninguém leva nada.
    """
    return delivery_ownership(order) == "house"


#: As duas vias do entregador, pelo nome que a casa usa:
#: **Identificada** (endereço, telefone, nome, cobrança na porta) e **Anônima**
#: (só o que identifica o pedido e confere a sacola).
COURIER_TICKET_IDENTIFIED = "identified"
COURIER_TICKET_ANONYMOUS = "anonymous"


def courier_ticket_variant(order) -> str:
    """Qual via do entregador este pedido imprime — e quem decide isso.

    **A configuração decide onde há escolha.** O canal de venda declara a via em
    ``ChannelConfig.fulfillment.courier_ticket``: o canal próprio imprime a
    Identificada (a transportadora contratada pela casa não tem app — o endereço
    só existe para ela no papel), o canal de marketplace imprime a Anônima.
    Canal novo entra por configuração, sem tocar nesta função.

    **A regra de terceiro trava onde não há escolha.** Configuração é do
    operador, e operador erra: um canal de marketplace deixado como
    ``identified`` mandaria endereço, telefone e nome do cliente para a mão de um
    entregador que trabalha para outra empresa. O iFood proíbe isso em documento
    destinado a parceiro de entrega, e a casa não tem interesse em espalhar dado
    de cliente. Então a configuração não é obedecida calada: quando o PEDIDO diz
    que quem entrega não é a casa (:func:`delivery_ownership`), prevalece a
    Anônima, e o log diz de quem era a escolha e por que ela caiu.

    ``unknown`` desce junto com ``marketplace``, pela regra desta casa: na dúvida
    não se repete dado pessoal. Responsável não informado é falta de prova, e
    falta de prova não autoriza — o Gestor, aliás, nem despacha esse pedido
    (``AdvanceBlock.IFOOD_DELIVERY_UNKNOWN``).
    """
    from shopman.shop.config import ChannelConfig

    configured = str(
        ChannelConfig.for_channel(order.channel_ref or "").fulfillment.courier_ticket
        or COURIER_TICKET_IDENTIFIED
    )
    if configured == COURIER_TICKET_ANONYMOUS:
        return COURIER_TICKET_ANONYMOUS

    ownership = delivery_ownership(order)
    if get_fulfillment_type(order) == "delivery" and ownership != "house":
        # ⚠️ A razão ANTES do retorno, e não depois: quem lê o log precisa saber
        # que a via saiu Anônima contra a configuração do canal, e não por
        # escolha de alguém. Sem esta linha a correção iria para o lugar errado
        # — alguém mexeria no papel em vez de arrumar o canal.
        logger.warning(
            "Via do entregador ANÔNIMA no pedido %s: o canal '%s' está configurado como "
            "'identified', mas a entrega deste pedido é de terceiro (%s). Endereço, "
            "telefone e nome do cliente não saem no papel. Corrija "
            "fulfillment.courier_ticket do canal.",
            order.ref,
            order.channel_ref or "",
            ownership,
        )
        return COURIER_TICKET_ANONYMOUS
    return COURIER_TICKET_IDENTIFIED


def exclude_test_orders(queryset):
    """Tira os pedidos de teste de um queryset de ``Order``.

    Gêmea de :func:`is_test_order` no banco, para leitores financeiros (B.I.).
    A negação de JSON tem semântica de três valores no SQLite e no PostgreSQL:
    um ``exclude`` simples também derrubaria a linha em que a chave não existe
    — isto é, todo pedido que não veio do iFood. O ramo nulo é escrito à mão
    para que só a marca exata desapareça.
    """
    from django.db.models import Q

    return queryset.filter(
        Q(data__ifood__is_test__isnull=True) | ~Q(data__ifood__is_test=True),
    )


def delivery_eta_minutes(shop, order_data: dict) -> float:
    """Minutos estimados de entrega a partir da SAÍDA.

    Percurso (distância ÷ velocidade urbana efetiva) + folga fixa (saída,
    trânsito, achar o endereço, handoff). Couriers terceirizados/sem rastreio,
    então é estimativa honesta por configuração. Calibrável em
    ``Shop.defaults["delivery"]``: ``avg_speed_kmh`` (18), ``handoff_buffer_minutes``
    (12), ``estimated_minutes`` (40 — fallback quando não há distância).
    """
    cfg = (getattr(shop, "defaults", None) or {}).get("delivery") or {}
    distance_km = (order_data or {}).get("delivery_distance_km")
    if distance_km:
        speed = float(cfg.get("avg_speed_kmh") or 18)
        buffer_minutes = float(cfg.get("handoff_buffer_minutes") or 12)
        if speed > 0:
            return buffer_minutes + (float(distance_km) / speed) * 60.0
    return float(cfg.get("estimated_minutes") or 40)


def delivery_auto_complete_grace_minutes(shop) -> int:
    """Folga após o ETA antes de auto-concluir um pedido em entrega (rede de
    segurança se nem cliente nem operador fecharem). Calibrável em
    ``Shop.defaults["delivery"]["auto_complete_grace_minutes"]`` (default 30).
    ``0`` ou negativo DESLIGA a auto-conclusão."""
    cfg = (getattr(shop, "defaults", None) or {}).get("delivery") or {}
    raw = cfg.get("auto_complete_grace_minutes")
    return int(raw) if raw is not None else 30


def card_machine_alert_minutes(shop) -> int:
    """Quanto tempo a maquininha pode ficar na rua antes de virar alerta.
    Calibrável em ``Shop.defaults["delivery"]["card_machine_alert_minutes"]``
    (default 120). ``0`` ou negativo DESLIGA o alerta."""
    cfg = (getattr(shop, "defaults", None) or {}).get("delivery") or {}
    raw = cfg.get("card_machine_alert_minutes")
    return int(raw) if raw is not None else 120


def parse_commitment_date(value) -> date | None:
    """Parse an ISO delivery date into a ``date`` object."""
    if isinstance(value, date):
        return value
    if not value:
        return None
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def get_commitment_date(source) -> date | None:
    """Return the committed fulfillment date from an order/session/data dict."""
    if source is None:
        return None

    if isinstance(source, dict):
        data = source
    else:
        data = getattr(source, "data", None) or {}

    return parse_commitment_date(data.get("delivery_date"))


def customer_holds_the_goods(order) -> bool:
    """Venda de balcão presencial: a mercadoria já está na mão do cliente?

    É a pergunta que decide duas coisas, e por isso tem UMA resposta: se a
    venda fecha no ato (``lifecycle`` — ``system:counter_handoff``) e se o pão
    de prateleira vira ticket de separação (``kds`` — ``prep_only``). Enquanto
    cada um respondia por conta própria, uma regra nova entrava num e faltava
    no outro.

    PDV, retirada, fora de Encomendas e sem data futura. Pix e cartão de
    gateway só representam entrega após captura suficiente; o link continua
    remoto mesmo depois de pago. Crédito/débito de maquininha e dinheiro
    preservam o fluxo presencial atestado pelo operador.
    """
    data = order.data or {}
    # O snapshot já contém o contexto da sessão ao nascer o pedido. O carimbo
    # operacional em order.data.pos só é completado após os callbacks do commit;
    # a decisão de entregar/separar não pode esperar por ele.
    snapshot_data = (getattr(order, "snapshot", None) or {}).get("data") or {}
    mode = (data.get("pos") or {}).get("sales_mode") or (snapshot_data.get("pos") or {}).get("sales_mode")
    if mode == "order":
        return False
    if data.get("origin_channel") != "pos":
        return False
    if (data.get("fulfillment_type") or "pickup") != "pickup":
        return False
    payment = data.get("payment") or {}
    method = str(payment.get("method") or "").strip().lower()
    if method == "link":
        return False
    if method in {"pix", "card"}:
        from shopman.shop.services.payment_gate import payment_is_captured

        if not payment_is_captured(order):
            return False
    commitment = get_commitment_date(order)
    if commitment and commitment > timezone.localdate():
        return False
    # O pão que ainda está no FORNO não está na mão de ninguém. Sem este corte
    # a venda de balcão de um item que só existe como fornada planejada fechava
    # ``COMPLETED`` no ato (``system:counter_handoff``) e mandava baixar
    # estoque de um lote que não saiu — o `fulfill_hold` falhava e o operador
    # recebia um alerta CRÍTICO de "estoque acima do físico" pela venda mais
    # normal da padaria. Pior que o alerta: o pedido nascia e morria no mesmo
    # instante, então ninguém no gestor sabia que havia um cliente esperando
    # uma fornada. Com o corte ele fica em fermata e o board já diz
    # "Esperando o lote…".
    from shopman.shop.services import waitlist

    return not waitlist.is_in_fermata(order)


def merge_order_data(order, values: dict, *, block: str | None = None, remove: tuple[str, ...] = ()) -> None:
    """Atualiza somente campos do writer sobre JSON fresco, sob lock de Order.

    Utilitário local: sem rede, eventos ou inferência de status. Callers continuam
    responsáveis por causalidade/idempotência de seus efeitos e por revalidar o
    próprio bloco quando a alteração depende de uma versão anterior.
    """
    from django.db import transaction
    from shopman.orderman.models import Order

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        data = dict(locked.data or {})
        target = dict(data.get(block) or {}) if block else data
        target.update(values)
        for key in remove:
            target.pop(key, None)
        if block:
            data[block] = target
        locked.data = data
        locked.save(update_fields=["data", "updated_at"])
        order.data = data


def json_quantity(value) -> int | str:
    """Keep integral JSON compatibility without truncating exact fractional goods."""
    from decimal import Decimal

    quantity = Decimal(str(value))
    if not quantity.is_finite():
        raise ValueError("Quantidade inválida")
    if quantity == quantity.to_integral_value():
        return int(quantity)
    return format(quantity.normalize(), "f")
