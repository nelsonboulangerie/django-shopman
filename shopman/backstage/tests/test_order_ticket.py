"""A filipeta do pedido remoto — o papel que vai para o painel de parede.

Ela sai ANTES do pagamento, e é isso que separa esta suíte da do recibo: um
papel com total impresso, entregue antes de o dinheiro entrar, passa por
comprovante de pagamento se não disser o contrário. Os testes abaixo prendem as
três coisas que a filipeta não pode perder de vista — o que ela diz que NÃO é,
os dois vocabulários da janela combinada, e o carimbo de segunda via.
"""

from __future__ import annotations

import base64
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.services import order_ticket as tickets
from shopman.backstage.services.receipt_escpos import COLUMNS, ENCODING, order_ticket
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


# ── Cenário ───────────────────────────────────────────────────────────────


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Nelson Boulangerie")


def _order(ref: str, *, status: str = "accepted", items=(("Pão de fermentação natural", 2, 1800),), **data_extra) -> Order:
    data = {"customer": {"name": "Ana"}, "payment": {"method": "link"}}
    data.update(data_extra)
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=status,
        total_q=sum(qty * price for _, qty, price in items),
        data=data,
    )
    for seq, (name, qty, price) in enumerate(items, start=1):
        OrderItem.objects.create(
            order=order,
            line_id=str(seq),
            sku=f"SKU-{seq}",
            name=name,
            qty=qty,
            unit_price_q=price,
            line_total_q=qty * price,
        )
    return order


def _texto(papel: bytes) -> str:
    return papel.decode(ENCODING, "replace")


def _linhas(papel: bytes) -> list[str]:
    """As linhas do papel SEM os bytes de controle de corpo duplo.

    ``GS ! n`` vive colado ao texto da linha que ele engorda; deixá-lo dentro
    faria toda asserção sobre a linha de destaque procurar caracteres de
    controle junto com o texto.
    """
    limpo = _texto(papel).replace("\x1d!\x11", "").replace("\x1d!\x00", "")
    return [linha.rstrip() for linha in limpo.split("\n")]


# ── O que ela DIZ QUE NÃO É ───────────────────────────────────────────────


def test_a_filipeta_diz_que_nao_e_nota_nem_comprovante_de_pagamento(shop):
    """⚠️ Ela nasce antes do pagamento e traz um total impresso.

    Sem estas duas frases, um papel com "TOTAL R$ 36,00" na mão do cliente é
    indistinguível de um recibo — e quem o guarda tem toda a razão em achar que
    já pagou.
    """
    papel = _texto(order_ticket(_order("ORD-T1")))

    assert "não é documento fiscal" in papel
    assert "não comprova pagamento" in papel


def test_pedido_em_ABERTO_grita_que_o_pagamento_esta_pendente(shop):
    papel = _texto(order_ticket(_order("ORD-T2")))

    assert "*** PAGAMENTO PENDENTE ***" in papel


def test_pedido_PAGO_nao_grita_pendencia(shop):
    """O aviso é sobre este pedido, não decoração do leiaute."""
    pago = _order("ORD-T3", payment={"method": "pix", "status": "captured"})

    papel = _texto(order_ticket(pago))

    assert "PAGAMENTO PENDENTE" not in papel
    assert "Pago" in papel


# ── O bloco que se lê de longe ────────────────────────────────────────────


def test_o_papel_destaca_dia_janela_recebimento_e_nome(shop):
    """O painel é físico e se lê a metros. Estes quatro são o que se lê de longe."""
    amanha = timezone.localdate() + timedelta(days=1)
    order = _order(
        "ORD-T4",
        delivery_date=amanha.isoformat(),
        delivery_time_slot="slot-12",
        fulfillment_type="delivery",
        customer={"name": "Ana"},
    )

    destaque = [linha.strip() for linha in _linhas(order_ticket(order)) if "\x1d" not in linha]

    assert "AMANHÃ" in destaque
    assert "A PARTIR DAS 12H" in destaque
    assert "ENTREGA" in destaque
    assert "Ana" in destaque


def test_retirada_e_entrega_nao_se_parecem_no_papel(shop):
    retirada = _order("ORD-T5", fulfillment_type="pickup")
    entrega = _order("ORD-T6", fulfillment_type="delivery")

    assert "RETIRADA" in _texto(order_ticket(retirada))
    assert "ENTREGA" in _texto(order_ticket(entrega))


def test_nome_comprido_encurta_pelo_MEIO_e_nao_pelo_fim(shop):
    """"Maria Aparecida da Silva Xavier" cortado no fim é o nome de ninguém."""
    order = _order("ORD-T7", customer={"name": "Maria Aparecida da Silva Xavier"})

    papel = _texto(order_ticket(order))

    assert "Maria Xavier" in papel
    # O nome inteiro continua no corpo — o encurtamento é só do destaque.
    assert "Cliente: Maria Aparecida da Silva Xavier" in papel


# ── ⚠️ Os DOIS vocabulários de `delivery_time_slot` ───────────────────────


def test_a_ENCOMENDA_imprime_o_rotulo_do_slot_e_NUNCA_o_ref(shop):
    """⚠️ ``"slot-09"`` na cara do cliente é identificador vazando.

    A chave carrega dois vocabulários (data-schemas) e quem imprime tem de
    tolerar os dois. Este é o lado da encomenda: ref canônico.
    """
    order = _order(
        "ORD-T8",
        delivery_date=(timezone.localdate() + timedelta(days=3)).isoformat(),
        delivery_time_slot="slot-09",
    )

    papel = _texto(order_ticket(order))

    assert "A PARTIR DAS 09H" in papel
    assert "slot-09" not in papel.lower()


def test_a_venda_do_DIA_no_PDV_imprime_o_par_de_horas(shop):
    """O outro lado da mesma chave: a meia hora do expediente, que se lê sozinha."""
    order = _order(
        "ORD-T9",
        delivery_date=timezone.localdate().isoformat(),
        delivery_time_slot="14:00-14:30",
    )

    papel = _texto(order_ticket(order))

    assert "14:00 ÀS 14:30" in papel


def test_janela_desconhecida_sai_crua_em_vez_de_sumir(shop):
    """Ref cru é feio; janela em branco é o compromisso sumindo do papel."""
    order = _order("ORD-T10", delivery_time_slot="slot-inexistente")

    assert "SLOT-INEXISTENTE" in _texto(order_ticket(order))


# ── ⚠️ O pedido SEM agendamento ───────────────────────────────────────────


def test_pedido_sem_data_combinada_nao_finge_ser_de_hoje(shop):
    """⚠️ Não existe campo ``scheduled_for``; a ausência é `delivery_date` vazia.

    Chamar de "HOJE" o pedido que ninguém agendou o jogaria para o topo do
    painel como trabalho de agora. Ele diz o que é.
    """
    order = _order("ORD-T11")

    papel = _texto(order_ticket(order))

    assert "SEM AGENDAMENTO" in papel
    assert "HOJE" not in papel


def test_pedido_de_HOJE_diz_hoje(shop):
    order = _order("ORD-T12", delivery_date=timezone.localdate().isoformat())

    assert "HOJE" in _texto(order_ticket(order))


# ── O corpo ───────────────────────────────────────────────────────────────


def test_o_papel_traz_itens_endereco_e_as_DUAS_notas_com_nome(shop):
    """As notas são de donos diferentes: o cliente pediu, a cozinha anotou."""
    order = _order(
        "ORD-T13",
        items=(("Croissant de amêndoas", 3, 1200),),
        fulfillment_type="delivery",
        delivery_address="Rua das Flores, 123",
        delivery_address_structured={"complement": "apto 42", "delivery_instructions": "portão azul"},
        order_notes="Sem cebola, por favor",
        kitchen_note="Embalar separado",
    )

    papel = _texto(order_ticket(order))

    assert "3 x Croissant de amêndoas" in papel
    assert "Rua das Flores, 123 - apto 42" in papel
    assert "Referência: portão azul" in papel
    assert "Observação do cliente:" in papel
    assert "Sem cebola, por favor" in papel
    assert "Nota da cozinha:" in papel
    assert "Embalar separado" in papel


def test_a_retirada_nao_imprime_bloco_de_endereco(shop):
    order = _order("ORD-T14", fulfillment_type="pickup", delivery_address="Rua das Flores, 123")

    assert "ENTREGAR EM:" not in _texto(order_ticket(order))


def test_o_valor_da_linha_sai_INTEIRO_mesmo_na_encomenda_de_festa(shop):
    """⚠️ "R$ 12.345,67" tem 12 colunas; goteira apertada comeria o último dígito."""
    order = _order("ORD-T15b", items=(("Pão de fermentação natural com sementes", 29, 42_571),))

    assert "R$ 12.345,59" in _texto(order_ticket(order))


def test_nenhuma_linha_passa_de_48_colunas(shop):
    """48 colunas foram medidas com régua no papel; estourar é texto perdido."""
    order = _order(
        "ORD-T15",
        items=(("Pão de fermentação natural com sementes e castanhas do Pará", 12, 4250),),
        fulfillment_type="delivery",
        delivery_address="Rua Comendador Alberto Bonfiglioli Sobrinho, 1234, Jardim das Américas",
        order_notes="Por favor entregar depois das dezoito horas porque não tem ninguém em casa antes",
    )

    for linha in _linhas(order_ticket(order)):
        assert len(linha) <= COLUMNS, f"linha estourou a bobina: {linha!r}"


def test_o_papel_impoe_a_tabela_de_acento_e_reseta_a_impressora(shop):
    papel = order_ticket(_order("ORD-T16"))

    assert papel.startswith(bytes([0x1B, ord("@")])), "sem reset, herda estado do job anterior"
    assert bytes([0x1B, ord("t"), 3]) in papel
    assert papel.endswith(bytes([0x1D, ord("V"), 1])), "sem corte, a filipeta seguinte vem colada"


def test_o_QR_aponta_para_o_acompanhamento_do_pedido(shop, settings):
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://nelson.com.br"

    papel = tickets.ticket_bytes(_order("ORD-T17"))

    assert b"https://nelson.com.br/pedido/ORD-T17" in papel
    assert bytes([0x1D, 0x28, 0x6B]) in papel, "faltou o comando de QR"


def test_sem_base_de_loja_o_papel_sai_SEM_QR(shop, settings):
    """Melhor sem QR do que com um QR que não abre nada."""
    settings.SHOPMAN_STOREFRONT_BASE_URL = ""

    papel = tickets.ticket_bytes(_order("ORD-T18"))

    assert bytes([0x1D, 0x28, 0x6B]) not in papel


# ── A janela do lote ──────────────────────────────────────────────────────


def test_o_padrao_do_lote_e_a_semana_QUE_VEM(shop):
    """⚠️ Divergência deliberada do relatório de produção (7 dias para trás).

    O painel de filipetas pergunta o que a casa prometeu, não o que aconteceu.
    """
    hoje = timezone.localdate()

    date_from, date_to = tickets.parse_period(None, None)

    assert date_from == hoje
    assert date_to == hoje + timedelta(days=6)


def test_intervalo_invertido_e_TROCADO_e_nao_recusado(shop):
    date_from, date_to = tickets.parse_period("2026-09-10", "2026-09-04")

    assert (date_from.isoformat(), date_to.isoformat()) == ("2026-09-04", "2026-09-10")


def test_data_ilegivel_cai_no_padrao_em_vez_de_estourar(shop):
    hoje = timezone.localdate()

    date_from, date_to = tickets.parse_period("ontem", "2026-09-10")

    assert date_from == hoje
    assert date_to.isoformat() == "2026-09-10"


# ── O lote ────────────────────────────────────────────────────────────────


def test_o_lote_vai_pela_data_COMBINADA_e_nao_pela_data_da_venda(shop):
    """A encomenda feita hoje para sábado é filipeta de sábado."""
    hoje = timezone.localdate()
    sabado = hoje + timedelta(days=3)
    encomenda = _order("ORD-B1", delivery_date=sabado.isoformat())
    _order("ORD-B2", delivery_date=(hoje + timedelta(days=30)).isoformat())

    refs = [o.ref for o in tickets.orders_for_period(sabado, sabado)]

    assert refs == [encomenda.ref]


def test_pedido_sem_data_combinada_entra_pelo_dia_em_que_foi_feito(shop):
    hoje = timezone.localdate()
    order = _order("ORD-B3")

    refs = [o.ref for o in tickets.orders_for_period(hoje, hoje)]

    assert order.ref in refs


def test_o_lote_sai_na_ordem_do_PAINEL_dia_e_depois_hora(shop):
    hoje = timezone.localdate()
    amanha = hoje + timedelta(days=1)
    _order("ORD-B-TARDE", delivery_date=hoje.isoformat(), delivery_time_slot="slot-15")
    _order("ORD-B-CEDO", delivery_date=hoje.isoformat(), delivery_time_slot="slot-09")
    _order("ORD-B-AMANHA", delivery_date=amanha.isoformat(), delivery_time_slot="slot-09")

    refs = [o.ref for o in tickets.orders_for_period(hoje, amanha)]

    assert refs == ["ORD-B-CEDO", "ORD-B-TARDE", "ORD-B-AMANHA"]


def test_o_pedido_sem_janela_vai_para_o_FIM_do_dia_dele(shop):
    """Ausência de hora é "não combinado", não meia-noite."""
    hoje = timezone.localdate()
    _order("ORD-B-SEM-JANELA", delivery_date=hoje.isoformat())
    _order("ORD-B-COM-JANELA", delivery_date=hoje.isoformat(), delivery_time_slot="slot-15")

    refs = [o.ref for o in tickets.orders_for_period(hoje, hoje)]

    assert refs == ["ORD-B-COM-JANELA", "ORD-B-SEM-JANELA"]


def test_pedido_cancelado_nao_vai_para_a_parede(shop):
    hoje = timezone.localdate()
    _order("ORD-B-MORTO", status="cancelled", delivery_date=hoje.isoformat())

    assert tickets.orders_for_period(hoje, hoje) == []


def test_periodo_vazio_devolve_lista_vazia(shop):
    futuro = timezone.localdate() + timedelta(days=400)

    assert tickets.orders_for_period(futuro, futuro) == []


# ── Os endpoints ──────────────────────────────────────────────────────────


@pytest.fixture
def gestor(db, shop):
    """Operador do Gestor: staff + ``shop.manage_orders``, NÃO superusuário."""
    user = User.objects.create_user("gestor-filipeta", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"),
            codename="manage_orders",
        )
    )
    return user


@pytest.fixture
def logado(client, gestor):
    client.force_login(gestor)
    return client


def test_o_servidor_entrega_os_bytes_prontos_de_UMA_filipeta(logado, shop):
    """A tela relaia; ela não sabe compor ESC/POS nem precisa saber."""
    order = _order("ORD-E1")

    corpo = logado.get(reverse("api-backstage-order-ticket-escpos", args=[order.ref])).json()

    papel = base64.b64decode(corpo["payload_b64"])
    assert papel.startswith(bytes([0x1B, 0x40]))
    assert corpo["title"] == "filipeta:ORD-E1"
    assert corpo["reprint"] is False


def test_filipeta_de_pedido_inexistente_e_404(logado, shop):
    assert logado.get(reverse("api-backstage-order-ticket-escpos", args=["NAO-EXISTE"])).status_code == 404


def test_staff_SEM_manage_orders_nao_imprime_filipeta(client, db, shop):
    User.objects.create_user("sem-permissao", password="pw", is_staff=True)
    client.login(username="sem-permissao", password="pw")
    order = _order("ORD-E2")

    resposta = client.get(reverse("api-backstage-order-ticket-escpos", args=[order.ref]))

    assert resposta.status_code in (401, 403)


# ── ⚠️ O carimbo de segunda via ───────────────────────────────────────────


def test_a_SEGUNDA_composicao_sai_carimbada(logado, shop):
    """Sem a marca, o painel ganha uma cópia que passa por original."""
    order = _order("ORD-E3")
    url = reverse("api-backstage-order-ticket-escpos", args=[order.ref])

    primeira = logado.get(url).json()
    segunda = logado.get(url).json()

    assert primeira["reprint"] is False
    assert segunda["reprint"] is True
    assert "2a VIA" in _texto(base64.b64decode(segunda["payload_b64"]))
    assert "2a VIA" not in _texto(base64.b64decode(primeira["payload_b64"]))


def test_o_carimbo_fica_gravado_no_pedido(logado, shop):
    order = _order("ORD-E4")

    logado.get(reverse("api-backstage-order-ticket-escpos", args=[order.ref]))

    order.refresh_from_db()
    assert order.data["ticket_printed_at"]


def test_a_conferencia_do_lote_NAO_carimba(logado, shop):
    """Olhar não é imprimir — a tela precisa poder contar antes do gesto."""
    hoje = timezone.localdate()
    order = _order("ORD-E5", delivery_date=hoje.isoformat())

    corpo = logado.get(
        reverse("api-backstage-order-tickets"),
        {"date_from": hoje.isoformat(), "date_to": hoje.isoformat()},
    ).json()

    assert corpo["count"] == 1
    assert corpo["orders"][0]["ref"] == order.ref
    assert corpo["orders"][0]["already_printed"] is False
    order.refresh_from_db()
    assert "ticket_printed_at" not in (order.data or {})


def test_o_lote_carimba_pedido_a_pedido(logado, shop):
    hoje = timezone.localdate()
    ja_impresso = _order("ORD-E6", delivery_date=hoje.isoformat())
    ja_impresso.data["ticket_printed_at"] = timezone.now().isoformat()
    ja_impresso.save(update_fields=["data"])
    novo = _order("ORD-E7", delivery_date=hoje.isoformat())

    corpo = logado.get(
        reverse("api-backstage-order-tickets-escpos"),
        {"date_from": hoje.isoformat(), "date_to": hoje.isoformat()},
    ).json()

    assert corpo["count"] == 2
    assert corpo["reprint_count"] == 1
    assert set(corpo["refs"]) == {ja_impresso.ref, novo.ref}
    novo.refresh_from_db()
    assert novo.data["ticket_printed_at"]


def test_o_lote_sai_como_filipetas_CONSECUTIVAS_num_trabalho_so(logado, shop):
    """Cada filipeta termina no corte parcial; um POST rende N papéis destacáveis."""
    hoje = timezone.localdate()
    _order("ORD-E8", delivery_date=hoje.isoformat())
    _order("ORD-E9", delivery_date=hoje.isoformat())

    corpo = logado.get(
        reverse("api-backstage-order-tickets-escpos"),
        {"date_from": hoje.isoformat(), "date_to": hoje.isoformat()},
    ).json()

    papel = base64.b64decode(corpo["payload_b64"])
    assert papel.count(bytes([0x1D, ord("V"), 1])) == 2
    assert b"ORD-E8" in papel and b"ORD-E9" in papel


def test_periodo_sem_pedido_devolve_lote_vazio(logado, shop):
    futuro = (timezone.localdate() + timedelta(days=400)).isoformat()

    corpo = logado.get(
        reverse("api-backstage-order-tickets-escpos"), {"date_from": futuro, "date_to": futuro}
    ).json()

    assert corpo["count"] == 0
    assert base64.b64decode(corpo["payload_b64"]) == b""


def test_lote_maior_que_a_bobina_e_RECUSADO_antes_de_carimbar(logado, shop, monkeypatch):
    """⚠️ O custo do intervalo digitado errado é o rolo inteiro no chão."""
    monkeypatch.setattr(tickets, "MAX_BATCH", 1)
    hoje = timezone.localdate()
    a = _order("ORD-E10", delivery_date=hoje.isoformat())
    _order("ORD-E11", delivery_date=hoje.isoformat())

    resposta = logado.get(
        reverse("api-backstage-order-tickets-escpos"),
        {"date_from": hoje.isoformat(), "date_to": hoje.isoformat()},
    )

    assert resposta.status_code == 409
    a.refresh_from_db()
    assert "ticket_printed_at" not in (a.data or {})


# ── A rota do lote não pode ser engolida pelo `<str:ref>` ─────────────────


def test_a_rota_do_lote_nao_e_confundida_com_um_ref_de_pedido(logado, shop):
    """⚠️ ``orders/tickets/`` casa com ``orders/<str:ref>/`` se vier depois."""
    resposta = logado.get(reverse("api-backstage-order-tickets"))

    assert resposta.status_code == 200
    assert "orders" in resposta.json()
