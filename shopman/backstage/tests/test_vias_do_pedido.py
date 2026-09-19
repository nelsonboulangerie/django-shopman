"""As vias do pedido: o registro, a oferta por contexto e os filtros de divulgação.

O dono cortou os papéis não fiscais da casa por AUDIÊNCIA, e são três: **Via
Cozinha** (o KDS materializado), **Via Pedido** (nasce no painel físico e
viaja com a sacola — um papel só, com duas fases de vida) e **Via Recibo** (quem
pagou). A "via do entregador" não é uma quarta: é a Via Pedido com o filtro
de identificação ligado.

Este arquivo trava três coisas do registro (``services.order_documents``), e
nenhuma delas é leiaute — papel tem dono em ``receipt_escpos``, e os testes dele
continuam onde estão:

1. **A oferta é por contexto**, e via sem papel não é oferecida.
2. **A permissão é POR VIA.** Quem opera a cozinha não alcança a Via Pedido
   nem a Via Recibo; quem não é do caixa não alcança o recibo.
3. **Os filtros são DERIVADOS**, nunca escolhidos por quem imprime — e cada um
   tem um piso que a configuração (ou o pedido do cliente) não fura.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.services import order_documents as vias
from shopman.shop.models import Channel, Shop
from shopman.shop.services import ifood_ingest, ifood_orders

pytestmark = pytest.mark.django_db


# ── Cenário ───────────────────────────────────────────────────────────────


@pytest.fixture
def shop(db):
    return Shop.objects.get_or_create(name="Nelson Boulangerie")[0]


@pytest.fixture
def canal_proprio(shop):
    """Canal da casa: o default da configuração mantém a identificação."""
    return Channel.objects.get_or_create(ref="web", defaults={"name": "Loja online"})[0]


@pytest.fixture
def canal_ifood(shop):
    """Canal de marketplace, configurado como no seed: sem identificação."""
    return Channel.objects.get_or_create(ref="ifood", defaults={
        "name": "iFood",
        "config": {
            "payment": {"method": "external", "timing": "external"},
            "fulfillment": {"courier_ticket": "anonymous"},
        },
    })[0]


def _pedido_da_casa(ref: str, **data_extra) -> Order:
    """Pedido do canal próprio: quem entrega é contratado pela loja."""
    data = {
        "fulfillment_type": "delivery",
        "customer": {"name": "Ana Ribeiro", "phone": "(43) 99911-2233"},
        "delivery_address": "Rua das Flores, 123",
        "payment": {"method": "link", "status": "pending"},
    }
    data.update(data_extra)
    order = Order.objects.create(ref=ref, channel_ref="web", status="accepted", total_q=3600, data=data)
    OrderItem.objects.create(
        order=order, line_id="1", sku="PAO-001", name="Pão de fermentação natural",
        qty=2, unit_price_q=1800, line_total_q=3600,
    )
    return order


def _pedido_do_ifood(
    order_id: str, *, delivered_by: str | None = "IFOOD", localizer: str = "9988"
) -> Order:
    """Pedido cru do iFood, do jeito que o Order Module v1.0 entrega, já ingerido."""
    delivery: dict = {
        "deliveryAddress": {"formattedAddress": "Rua das Flores, 123", "postalCode": "86020-000"},
        "pickupCode": "4521",
    }
    if delivered_by is not None:
        delivery["deliveredBy"] = delivered_by
    cru = {
        "id": order_id,
        "displayId": "8842",
        "isTest": False,
        "orderType": "DELIVERY",
        # ⚠️ O iFood não manda o telefone do cliente: manda um número já
        # mascarado por eles mais um localizador do relé de voz.
        "customer": {
            "name": "Ana Ribeiro",
            "phone": {"number": "(43) 99911-2233", "localizer": localizer},
        },
        "total": {"orderAmount": 45},
        "payments": {"prepaid": 45, "pending": 0,
                     "methods": [{"method": "CREDIT", "type": "ONLINE", "prepaid": True, "value": 45}]},
        "delivery": delivery,
        "items": [{"id": "item-1", "externalCode": "PAO-001", "name": "Pão francês",
                   "quantity": 1, "unitPrice": 45, "totalPrice": 45}],
    }
    with patch.object(ifood_ingest.order_changed, "send"):
        return ifood_ingest.ingest(ifood_orders.map_order(cru))


def _operador(username: str, *perms: str) -> User:
    """Operador com as permissões nomeadas — nunca superusuário.

    Superusuário responde ``True`` a tudo e transformaria os testes de permissão
    em testes de nada.

    As permissões são nomeadas como o registro as declara (``app.codename``),
    para que um erro de app_label no registro apareça AQUI, na montagem, e não
    como um botão silenciosamente ausente na tela.
    """
    user = User.objects.create_user(username, password="pw", is_staff=True)
    for code in perms:
        app_label, codename = code.split(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return user


@pytest.fixture
def gestor(db, shop):
    """Cuida da FILA: ``shop.manage_orders``, e mais nada."""
    return _operador("via-gestor", "shop.manage_orders")


@pytest.fixture
def caixa(db, shop):
    """Opera o balcão: as duas permissões que o grupo Caixa tem no seed."""
    return _operador("via-caixa", "shop.manage_orders", "cashman.operate_pos")


@pytest.fixture
def cozinha(db, shop):
    """Opera o preparo: ``backstage.operate_kds``, e mais nada."""
    return _operador("via-cozinha", "backstage.operate_kds")


def _chaves(offered) -> list[str]:
    return [via.key for via in offered]


def _uma(offered, key: str):
    return next(via for via in offered if via.key == key)


def _encomenda(order, actor, *, context=None):
    return _uma(
        vias.documents_for(order, context=context or vias.CONTEXT_DISPATCH, actor=actor),
        vias.ORDER,
    )


# ── 1. O registro: quem é cada via ────────────────────────────────────────


def test_o_catalogo_tem_tres_vias_por_audiencia():
    """Três audiências, três vias. A chave é quem LÊ o papel.

    ⚠️ "Painel" e "sacola" não são vias diferentes — são duas fases da Via
    Pedido. E "via do entregador" não é uma via: é a Via Pedido com o
    filtro de identificação ligado.
    """
    assert _chaves(vias.DOCUMENTS) == [vias.KITCHEN, vias.ORDER, vias.RECEIPT]
    assert set(vias.BY_KEY) == {vias.KITCHEN, vias.ORDER, vias.RECEIPT}


def test_cada_via_carrega_a_propria_permissao():
    """⚠️ Colapsar as permissões daria a quem opera o caixa o endereço do
    cliente de qualquer pedido — e à cozinha, o recibo da venda."""
    assert vias.BY_KEY[vias.RECEIPT].permission == "cashman.operate_pos"
    assert vias.BY_KEY[vias.ORDER].permission == "shop.manage_orders"
    assert vias.BY_KEY[vias.KITCHEN].permission == "backstage.operate_kds"


def test_as_quatro_chaves_de_carimbo_continuam_quatro():
    """⚠️ A Via Pedido é um papel só e tem DUAS chaves, porque são duas
    fases: "a ficha já ter ido para o painel não faz da primeira via do
    entregador uma segunda". Unificar faria a primeira via que sai pela porta
    nascer marcada como reimpressão de um papel que ninguém segurou."""
    encomenda = vias.BY_KEY[vias.ORDER]
    assert encomenda.print_stamp_key == "ticket_printed_at"
    assert encomenda.filtered_print_stamp_keys == {
        vias.FILTER_CUSTOMER_IDENTITY: "courier_ticket_printed_at",
    }
    assert vias.BY_KEY[vias.RECEIPT].print_stamp_key == "receipt_printed_at"
    assert vias.BY_KEY[vias.KITCHEN].print_stamp_key == "kitchen_ticket_printed_at"

    todas = {d.print_stamp_key for d in vias.DOCUMENTS}
    todas |= {k for d in vias.DOCUMENTS for k in d.filtered_print_stamp_keys.values()}
    assert todas == {
        "ticket_printed_at",
        "courier_ticket_printed_at",
        "receipt_printed_at",
        "kitchen_ticket_printed_at",
    }


def test_a_rota_declarada_por_cada_via_com_papel_existe(shop):
    """Rota declarada que não resolve é botão que responde 404."""
    for document in vias.DOCUMENTS:
        if not document.has_paper:
            continue
        assert reverse(document.route_name, args=["ORD-1"])
        for rota in document.filtered_route_names.values():
            assert reverse(rota, args=["ORD-1"])


def test_so_o_recibo_tem_superficie_alternativa():
    """O recibo tem gêmeo em TypeScript (``presentation/receipt.ts`` +
    ``PosReceipt.vue``); as outras vias não têm gêmea em HTML de propósito —
    inventar uma criaria um segundo leiaute com um segundo dono."""
    com_alternativa = [d.key for d in vias.DOCUMENTS if d.alternate_surface]
    assert com_alternativa == [vias.RECEIPT]


def test_a_via_da_cozinha_esta_registrada_mas_ainda_nao_tem_papel():
    """O catálogo é a decisão; o papel é a migração, que vem depois."""
    cozinha_via = vias.BY_KEY[vias.KITCHEN]
    assert cozinha_via.has_paper is False
    assert cozinha_via.route_name == ""
    # A chave do carimbo já está reservada para a migração não escolher um nome
    # sob pressão — e para ninguém escolher outro.
    assert cozinha_via.print_stamp_key == "kitchen_ticket_printed_at"


# ── 2. Os filtros são uma FAMÍLIA, não dois casos especiais ───────────────


def test_os_dois_filtros_tem_a_mesma_forma():
    """Mesma máquina: chave, rótulo, a origem declarada e uma pergunta que
    recebe o PEDIDO e só o pedido. É isso que os mantém ortogonais."""
    assert [f.key for f in vias.FILTERS] == [
        vias.FILTER_CUSTOMER_IDENTITY,
        vias.FILTER_VALUES,
    ]
    for item in vias.FILTERS:
        assert item.label and item.source
        assert callable(item.resolve)


def test_a_via_que_sai_da_casa_e_a_unica_sujeita_aos_dois_filtros():
    """Ortogonal não quer dizer que todo filtro morde toda via.

    O recibo é a prova do pagamento — esconder valor ali o destrói, e o dado do
    cliente no papel do próprio cliente não é divulgação. A Via Cozinha não
    carrega contato de entrega nem dinheiro. Filtro vazio aqui é declaração, não
    esquecimento.
    """
    assert set(vias.BY_KEY[vias.ORDER].filters) == {
        vias.FILTER_CUSTOMER_IDENTITY,
        vias.FILTER_VALUES,
    }
    assert vias.BY_KEY[vias.RECEIPT].filters == ()
    assert vias.BY_KEY[vias.KITCHEN].filters == ()


def test_filtro_ligado_no_pedido_nao_morde_via_que_nao_esta_sujeita(canal_ifood, caixa):
    """Pedido de marketplace que também é presente sem valores: os dois filtros
    estão ligados NO PEDIDO, e o recibo não muda."""
    order = _pedido_do_ifood("ifood-ortogonal")
    order.data = {**order.data, "is_gift": True, "gift_hide_values": True}
    order.save(update_fields=["data"])

    recibo = _uma(
        vias.documents_for(order, context=vias.CONTEXT_ORDER_CARD, actor=caixa), vias.RECEIPT
    )

    assert recibo.applied_filters == frozenset()
    assert recibo.headline == "Via Recibo"


# ── 3. A oferta por contexto ──────────────────────────────────────────────


def test_o_fechamento_do_pdv_oferece_o_recibo(canal_proprio, caixa):
    order = _pedido_da_casa("ORD-CTX-PDV")

    oferecidas = vias.documents_for(order, context=vias.CONTEXT_POS_CHECKOUT, actor=caixa)

    assert _chaves(oferecidas) == [vias.RECEIPT]


def test_o_card_do_gestor_oferece_a_encomenda_e_o_recibo(canal_proprio, caixa):
    """Ordem de dentro da casa para fora."""
    order = _pedido_da_casa("ORD-CTX-CARD")

    oferecidas = vias.documents_for(order, context=vias.CONTEXT_ORDER_CARD, actor=caixa)

    assert _chaves(oferecidas) == [vias.ORDER, vias.RECEIPT]


def test_o_painel_e_o_despacho_oferecem_a_mesma_via(canal_proprio, caixa):
    """⚠️ Duas FASES da mesma via, não duas vias. O painel e o despacho pedem o
    mesmo papel; o que muda entre eles é a hora, não o documento."""
    order = _pedido_da_casa("ORD-CTX-FASES")

    no_painel = vias.documents_for(order, context=vias.CONTEXT_ORDER_PANEL, actor=caixa)
    no_despacho = vias.documents_for(order, context=vias.CONTEXT_DISPATCH, actor=caixa)

    assert _chaves(no_painel) == [vias.ORDER]
    assert _chaves(no_despacho) == [vias.ORDER]


def test_o_posto_da_cozinha_nao_oferece_nada_enquanto_a_via_nao_tem_papel(canal_proprio, cozinha):
    """⚠️ Botão que responde 404 é pior do que botão ausente."""
    order = _pedido_da_casa("ORD-CTX-COZINHA")

    oferecidas = vias.documents_for(order, context=vias.CONTEXT_KITCHEN_STATION, actor=cozinha)

    assert oferecidas == []


def test_contexto_desconhecido_nao_oferece_nada(canal_proprio, caixa):
    order = _pedido_da_casa("ORD-CTX-NADA")

    assert vias.documents_for(order, context="tela-que-nao-existe", actor=caixa) == []


# ── 4. A permissão é por via ──────────────────────────────────────────────


def test_quem_cuida_da_fila_sem_ser_do_caixa_nao_ve_o_recibo(canal_proprio, gestor):
    """A permissão do recibo é do CAIXA; a da Via Pedido é de quem cuida da
    fila. São gates diferentes porque são papéis de pessoas diferentes."""
    order = _pedido_da_casa("ORD-PERM-GESTOR")

    oferecidas = vias.documents_for(order, context=vias.CONTEXT_ORDER_CARD, actor=gestor)

    assert _chaves(oferecidas) == [vias.ORDER]


def test_quem_opera_a_cozinha_nao_alcanca_o_pedido_do_cliente(canal_proprio, cozinha):
    """⚠️ A separação mais dura das três: o posto de preparo não alcança nem
    endereço de cliente nem recibo de venda."""
    order = _pedido_da_casa("ORD-PERM-COZINHA")

    oferecidas = vias.documents_for(order, context=vias.CONTEXT_ORDER_CARD, actor=cozinha)

    assert oferecidas == []


def test_sem_operador_nao_se_oferece_via_nenhuma(canal_proprio):
    """Falha fechado: "não sei quem é" nunca foi autorização."""
    order = _pedido_da_casa("ORD-PERM-ANONIMO")

    assert vias.documents_for(order, context=vias.CONTEXT_ORDER_CARD, actor=None) == []


def test_nenhuma_via_e_oferecida_a_quem_nao_tem_a_permissao_dela(canal_proprio, db, shop):
    """Varredura: nenhum contexto vaza via nenhuma para quem não tem nada."""
    order = _pedido_da_casa("ORD-PERM-VARREDURA")
    balconista = User.objects.create_user("via-sem-nada", password="pw")
    contextos = {ctx for document in vias.DOCUMENTS for ctx in document.contexts}

    for contexto in contextos:
        assert vias.documents_for(order, context=contexto, actor=balconista) == [], contexto


# ── 5. Filtro: identificação do cliente ───────────────────────────────────


def test_no_canal_proprio_a_encomenda_leva_o_que_faz_a_entrega_acontecer(canal_proprio, gestor):
    """A transportadora contratada pela casa não tem app: o endereço só existe
    para ela no papel."""
    encomenda = _encomenda(_pedido_da_casa("ORD-ID-CASA"), gestor)

    assert encomenda.hides_customer_identity is False
    assert encomenda.headline == "Via Pedido"
    assert encomenda.print_stamp_key == "ticket_printed_at"
    assert encomenda.route_name == "api-backstage-order-ticket-escpos"


def test_no_marketplace_a_encomenda_sai_sem_identificacao_do_cliente(canal_ifood, gestor):
    """⚠️ A "via do entregador" é ISTO: a mesma via, com um filtro ligado — e
    por isso com carimbo e rota próprios, que são os da fase que viaja."""
    encomenda = _encomenda(_pedido_do_ifood("ifood-id-1"), gestor)

    assert encomenda.hides_customer_identity is True
    assert encomenda.headline == "Via Pedido — sem identificação do cliente"
    assert encomenda.print_stamp_key == "courier_ticket_printed_at"
    assert encomenda.route_name == "api-backstage-order-courier-ticket-escpos"


def test_canal_mal_configurado_nao_vira_vazamento_de_dado_do_cliente(canal_ifood, gestor):
    """⚠️ O PISO. Configuração é do operador, e operador erra: um canal de
    marketplace deixado como identificado mandaria endereço, telefone e nome
    para a mão de um entregador de outra empresa. Quando o PEDIDO diz que quem
    entrega não é a casa, o filtro liga assim mesmo."""
    canal_ifood.config = {**canal_ifood.config, "fulfillment": {"courier_ticket": "identified"}}
    canal_ifood.save(update_fields=["config"])

    encomenda = _encomenda(_pedido_do_ifood("ifood-id-piso"), gestor)

    assert encomenda.hides_customer_identity is True
    assert encomenda.print_stamp_key == "courier_ticket_printed_at"


def test_o_piso_tambem_fecha_quando_o_responsavel_e_desconhecido(canal_ifood, gestor):
    """Responsável não informado é falta de prova, e falta de prova não
    autoriza repetir dado pessoal."""
    canal_ifood.config = {**canal_ifood.config, "fulfillment": {"courier_ticket": "identified"}}
    canal_ifood.save(update_fields=["config"])

    encomenda = _encomenda(_pedido_do_ifood("ifood-id-mudo", delivered_by=None), gestor)

    assert encomenda.hides_customer_identity is True


def test_o_piso_nao_castiga_a_entrega_que_e_mesmo_da_casa(canal_ifood, gestor):
    """Pedido do iFood entregue pela LOJA: o entregador é contratado dela e
    precisa do endereço. O piso é sobre terceiro, não sobre marketplace."""
    canal_ifood.config = {**canal_ifood.config, "fulfillment": {"courier_ticket": "identified"}}
    canal_ifood.save(update_fields=["config"])

    encomenda = _encomenda(_pedido_do_ifood("ifood-id-merchant", delivered_by="MERCHANT"), gestor)

    assert encomenda.hides_customer_identity is False


def test_na_retirada_a_identificacao_fica(canal_proprio, gestor):
    """Não há entregador numa retirada: não há terceiro de quem esconder."""
    encomenda = _encomenda(_pedido_da_casa("ORD-ID-RETIRADA", fulfillment_type="pickup"), gestor)

    assert encomenda.hides_customer_identity is False


def test_a_fase_no_painel_herda_o_filtro_do_pedido(canal_ifood, gestor):
    """⚠️ Consequência direta de "um papel só", e ela é deliberada: o filtro é
    do PEDIDO, não da fase. Num pedido cuja entrega é de terceiro, a Via
    Pedido já nasce sem o nome do cliente — inclusive enquanto está pregada
    na parede. O dia em que a fase voltar a mudar o conteúdo, ela volta como
    FASE, nunca como uma via a mais."""
    order = _pedido_do_ifood("ifood-id-painel")

    no_painel = _encomenda(order, gestor, context=vias.CONTEXT_ORDER_PANEL)
    no_despacho = _encomenda(order, gestor, context=vias.CONTEXT_DISPATCH)

    assert no_painel.applied_filters == no_despacho.applied_filters
    assert no_painel.hides_customer_identity is True


# ── 5b. O que SOBREVIVE ao filtro de identificação ────────────────────────


def test_o_localizador_sobrevive_ao_filtro_de_identificacao(canal_ifood, gestor):
    """⚠️ O filtro esconde QUEM é o cliente, não toda forma de falar com ele.

    O localizador do relé de voz não é nome, não é endereço e não é o telefone
    do cliente: é um código que liga para ele sem dizer quem ele é. A
    documentação de impressão do iFood pede justamente que ele saia na comanda.
    """
    encomenda = _encomenda(_pedido_do_ifood("ifood-relay-1"), gestor)

    assert encomenda.hides_customer_identity is True
    assert encomenda.anonymous_contact is not None
    assert encomenda.anonymous_contact.kind == vias.IFOOD_VOICE_RELAY
    assert encomenda.anonymous_contact.value == "9988"


def test_o_localizador_tambem_vale_com_o_filtro_desligado(canal_ifood, gestor):
    """⚠️ O número que o iFood manda JÁ vem mascarado por eles. Sem o
    localizador ninguém completa a ligação — nem na via identificada de um
    pedido de marketplace que a própria loja entrega."""
    canal_ifood.config = {**canal_ifood.config, "fulfillment": {"courier_ticket": "identified"}}
    canal_ifood.save(update_fields=["config"])

    encomenda = _encomenda(_pedido_do_ifood("ifood-relay-2", delivered_by="MERCHANT"), gestor)

    assert encomenda.hides_customer_identity is False
    assert encomenda.anonymous_contact is not None
    assert encomenda.anonymous_contact.value == "9988"


def test_no_canal_proprio_nao_ha_rele_e_a_ausencia_e_dita(canal_proprio, gestor):
    """"Não há relé" e "há um relé em branco" são coisas diferentes para quem
    vai imprimir — por isso a ausência é ``None``, nunca um contato vazio."""
    encomenda = _encomenda(_pedido_da_casa("ORD-SEM-RELE"), gestor)

    assert encomenda.anonymous_contact is None


def test_a_validade_do_localizador_e_desconhecida_ate_o_mapeamento_guardar(canal_ifood, gestor):
    """⚠️ O localizador VENCE, e o ``phone.localizerExpiration`` do iFood ainda
    não é guardado por ``ifood_orders._map_customer``. Vazio quer dizer "não
    sei", nunca "não vence": quem compuser o papel diz o que sabe."""
    encomenda = _encomenda(_pedido_do_ifood("ifood-relay-3"), gestor)

    assert encomenda.anonymous_contact.expires_at == ""


# ── 6. Filtro: valores ────────────────────────────────────────────────────


def test_o_presente_esconde_valores_na_via_que_acompanha_a_mercadoria(canal_proprio, caixa):
    """A marca é do CLIENTE, do checkout (``gift_hide_values``): ninguém no
    balcão liga ou desliga isso."""
    order = _pedido_da_casa("ORD-VAL-PRESENTE", is_gift=True, gift_hide_values=True)

    encomenda = _encomenda(order, caixa)

    assert encomenda.hides_values is True
    assert encomenda.headline == "Via Pedido — sem valores"


def test_o_recibo_de_quem_pagou_nunca_esconde_valor(canal_proprio, caixa):
    """Sem valor ele deixa de ser recibo — e quem pagou é o comprador, não o
    destinatário do presente."""
    order = _pedido_da_casa("ORD-VAL-RECIBO", is_gift=True, gift_hide_values=True)

    oferecidas = vias.documents_for(order, context=vias.CONTEXT_ORDER_CARD, actor=caixa)

    assert _uma(oferecidas, vias.RECEIPT).hides_values is False


def test_pedido_que_nao_e_presente_nao_esconde_valor_em_via_nenhuma(canal_proprio, caixa):
    order = _pedido_da_casa("ORD-VAL-COMUM")

    oferecidas = vias.documents_for(order, context=vias.CONTEXT_ORDER_CARD, actor=caixa)

    assert [via.hides_values for via in oferecidas] == [False, False]


def test_presente_com_cobranca_na_porta_mostra_o_que_ha_para_cobrar(canal_proprio, caixa):
    """⚠️ O PISO do segundo filtro. O que se cobra na porta não é valor do
    presente, é instrução: sem ele o entregador chega e pergunta — justamente o
    que o presente queria evitar."""
    order = _pedido_da_casa(
        "ORD-VAL-PISO",
        is_gift=True,
        gift_hide_values=True,
        payment={"method": "cash", "status": "pending", "collection": "on_delivery"},
    )

    # ⚠️ Não é `caplog`: o `LOGGING` desta casa não propaga `shopman.*` para a
    # raiz, e o handler do caplog vive lá. Perguntar ao logger do módulo mede o
    # que foi chamado — mesma leitura do teste da via do entregador.
    with patch.object(vias.logger, "warning") as aviso:
        encomenda = _encomenda(order, caixa)

    assert encomenda.hides_values is False
    # A razão fica no log: sem ela a correção iria para o leiaute em vez de ir
    # para a cobrança.
    assert aviso.call_count == 1, "o piso derrubou o pedido do cliente em silêncio"
    registro = aviso.call_args[0][0] % tuple(aviso.call_args[0][1:])
    assert "gift_hide_values" in registro
    assert order.ref in registro


def test_a_cobranca_ja_acertada_devolve_o_presente_ao_silencio(canal_proprio, caixa):
    """Acertado o dinheiro (``cod_settled_at``), não há mais o que instruir — e
    o pedido do cliente volta a valer."""
    order = _pedido_da_casa(
        "ORD-VAL-ACERTADO",
        is_gift=True,
        gift_hide_values=True,
        payment={
            "method": "cash", "status": "pending", "collection": "on_delivery",
            "cod_settled_at": "2026-09-19T10:00:00+00:00",
        },
    )

    assert _encomenda(order, caixa).hides_values is True


# ── 7. Os dois filtros juntos ─────────────────────────────────────────────


def test_os_dois_filtros_se_acumulam_sem_se_atrapalhar(canal_ifood, gestor):
    """Ortogonais de verdade: o presente do marketplace liga os dois, e o
    rótulo diz os dois, na ordem do registro."""
    order = _pedido_do_ifood("ifood-dois-filtros")
    order.data = {**order.data, "is_gift": True, "gift_hide_values": True}
    order.save(update_fields=["data"])

    encomenda = _encomenda(order, gestor)

    assert encomenda.applied_filters == {vias.FILTER_CUSTOMER_IDENTITY, vias.FILTER_VALUES}
    assert encomenda.headline == (
        "Via Pedido — sem identificação do cliente, sem valores"
    )
