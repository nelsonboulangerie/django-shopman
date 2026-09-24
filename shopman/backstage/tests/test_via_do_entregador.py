"""As duas vias do entregador — o único papel do trio que sai da casa pela porta.

O recibo é do cliente e a filipeta é da casa; esta vai na mão de quem leva, e é
por isso que ela tem uma regra que as outras não têm. O iFood determina que
documento destinado a parceiro de entrega não traga CPF nem endereço; a Nelson,
no canal próprio, entrega com transportadora contratada por ela — e ali o
entregador não tem app nenhum, só o papel.

Por isso são **duas vias com nome**, e não uma via com um ``if`` escondendo o
endereço: **Identificada** e **Anônima**. Quem escolhe é a configuração do canal
(``ChannelConfig.fulfillment.courier_ticket``), e quem trava é o pedido: canal
configurado como Identificada cuja entrega é de terceiro imprime Anônima assim
mesmo, com log. Configuração decide onde há escolha; regra de terceiro não é
escolha.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.services import order_ticket as tickets
from shopman.backstage.services.receipt_escpos import ENCODING, courier_ticket
from shopman.shop.models import Channel, Shop
from shopman.shop.services import ifood_ingest, ifood_orders
from shopman.shop.services.order_helpers import (
    courier_ticket_variant,
    delivery_ownership,
    house_owns_the_delivery,
)

pytestmark = pytest.mark.django_db


# ── Cenário ───────────────────────────────────────────────────────────────


@pytest.fixture
def shop(db):
    return Shop.objects.get_or_create(name="Nelson Boulangerie")[0]


@pytest.fixture
def canal_proprio(shop):
    """Canal da casa: o default da configuração é a via Identificada."""
    return Channel.objects.get_or_create(ref="web", defaults={"name": "Loja online"})[0]


@pytest.fixture
def canal_ifood(shop):
    """Canal de marketplace, configurado como no seed: via Anônima."""
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
        "delivery_address_structured": {
            "complement": "Apto 42, bloco B",
            "delivery_instructions": "portão azul ao lado da farmácia",
            "postal_code": "86020-000",
        },
        "payment": {"method": "link", "status": "pending"},
    }
    data.update(data_extra)
    order = Order.objects.create(ref=ref, channel_ref="web", status="accepted", total_q=3600, data=data)
    OrderItem.objects.create(
        order=order, line_id="1", sku="PAO-001", name="Pão de fermentação natural",
        qty=2, unit_price_q=1800, line_total_q=3600,
    )
    return order


_ENDERECO_IFOOD = {
    "formattedAddress": "Rua das Flores, 123",
    "complement": "Apto 42, bloco B",
    "reference": "portão azul ao lado da farmácia",
    "postalCode": "86020-000",
}


def _pedido_do_ifood(
    order_id: str, *, delivered_by: str | None = "IFOOD", payments: dict | None = None,
    is_test: bool = False, display_id: str = "8842", pickup_code: str = "4521",
) -> Order:
    """Pedido cru do iFood, do jeito que o Order Module v1.0 entrega, já ingerido."""
    delivery: dict = {"deliveryAddress": dict(_ENDERECO_IFOOD), "pickupCode": pickup_code}
    if delivered_by is not None:
        delivery["deliveredBy"] = delivered_by
    cru = {
        "id": order_id,
        "displayId": display_id,
        "isTest": is_test,
        "orderType": "DELIVERY",
        "customer": {"name": "Ana Ribeiro", "phone": {"number": "(43) 99911-2233"},
                     "documentNumber": "390.533.447-05"},
        "total": {"orderAmount": 45},
        "payments": payments or {"prepaid": 45, "pending": 0,
                                 "methods": [{"method": "CREDIT", "type": "ONLINE",
                                              "prepaid": True, "value": 45}]},
        "delivery": delivery,
        "items": [{"id": "item-1", "externalCode": "PAO-001", "name": "Pão francês",
                   "quantity": 1, "unitPrice": 45, "totalPrice": 45}],
    }
    with patch.object(ifood_ingest.order_changed, "send"):
        return ifood_ingest.ingest(ifood_orders.map_order(cru))


_DINHEIRO_COM_TROCO = {
    "pending": 45, "prepaid": 0,
    "methods": [{"method": "CASH", "type": "OFFLINE", "prepaid": False, "value": 45,
                 "cash": {"changeFor": 50}}],
}


def _papel(order: Order) -> str:
    return courier_ticket(order).decode(ENCODING, "replace")


# ── 1. A condição tem nome, e ela não é "se for iFood" ────────────────────


def test_a_entrega_do_canal_proprio_e_compromisso_da_casa(shop):
    """Transportadora contratada pela loja NÃO é terceiro com os dados do cliente.

    A Nelson usa Taon Delivery/Taxi Machine no canal próprio. O entregador não
    tem app nenhum: o endereço existe para ele só se estiver no papel.
    """
    order = _pedido_da_casa("ORD-CASA-1")

    assert delivery_ownership(order) == "house"
    assert house_owns_the_delivery(order) is True


def test_pedido_do_ifood_entregue_pela_loja_tambem_e_da_casa(canal_ifood):
    """A condição lê o DADO, não o canal: ``deliveredBy=MERCHANT`` é entrega da casa."""
    order = _pedido_do_ifood("IFOOD-MERCHANT", delivered_by="MERCHANT")

    assert delivery_ownership(order) == "house"
    assert house_owns_the_delivery(order) is True


def test_pedido_do_ifood_entregue_pelo_ifood_e_do_marketplace(canal_ifood):
    order = _pedido_do_ifood("IFOOD-DELES", delivered_by="IFOOD")

    assert delivery_ownership(order) == "marketplace"
    assert house_owns_the_delivery(order) is False


def test_responsavel_nao_informado_nao_autoriza_repetir_dado_pessoal(canal_ifood):
    """⚠️ Desconhecido não é autorização, é falta de prova.

    A mesma porta que ``_collection_on_delivery`` fecha para a cobrança.
    """
    order = _pedido_do_ifood("IFOOD-SEM-DONO", delivered_by=None)

    assert delivery_ownership(order) == "unknown"
    assert house_owns_the_delivery(order) is False


def test_retirada_nao_tem_dono_de_entrega(shop):
    order = _pedido_da_casa("ORD-RETIRADA", fulfillment_type="pickup")

    assert delivery_ownership(order) == "none"
    assert house_owns_the_delivery(order) is False


# ── 1b. Quem escolhe a via é a CONFIGURAÇÃO do canal ──────────────────────


def test_o_canal_proprio_imprime_a_via_identificada(canal_proprio):
    """Default da configuração, e é o certo: a transportadora da casa não tem app."""
    order = _pedido_da_casa("ORD-CFG-CASA")

    assert courier_ticket_variant(order) == "identified"
    assert "Via do entregador - Identificada" in _papel(order)


def test_o_canal_de_marketplace_imprime_a_via_anonima(canal_ifood):
    """Nenhum ``if`` no papel: o canal iFood declara ``courier_ticket: anonymous``."""
    order = _pedido_do_ifood("IFOOD-CFG", delivered_by="IFOOD")

    assert courier_ticket_variant(order) == "anonymous"
    assert "Via do entregador - Anônima" in _papel(order)


def test_canal_novo_escolhe_a_via_sem_tocar_em_codigo(canal_proprio):
    """A promessa do desenho: virar a chave é configuração, não deploy."""
    canal_proprio.config = {"fulfillment": {"courier_ticket": "anonymous"}}
    canal_proprio.save(update_fields=["config"])
    order = _pedido_da_casa("ORD-CFG-VIRADA")

    papel = _papel(order)

    assert courier_ticket_variant(order) == "anonymous"
    assert "Via do entregador - Anônima" in papel
    assert "Rua das Flores" not in papel


def test_via_configurada_invalida_e_recusada_na_leitura_do_canal(canal_proprio):
    """Valor que ninguém compõe não vira papel silencioso: ``validate()`` recusa."""
    from shopman.shop.config import ChannelConfig

    canal_proprio.config = {"fulfillment": {"courier_ticket": "identificada"}}
    canal_proprio.save(update_fields=["config"])

    with pytest.raises(ValueError, match="fulfillment.courier_ticket"):
        ChannelConfig.for_channel("web")


# ── 1c. O PISO que a configuração não fura ────────────────────────────────


def test_canal_mal_configurado_nao_vira_vazamento_de_dado_do_cliente(canal_ifood):
    """⚠️ Operador erra, e o erro não pode custar a privacidade do cliente.

    Canal de marketplace deixado como ``identified`` mandaria endereço, telefone
    e nome para a mão de um entregador que trabalha para outra empresa. Quando o
    PEDIDO diz que quem entrega é o marketplace, a via sai Anônima assim mesmo —
    e o log diz de quem era a escolha, para a correção ir para o canal e não
    para o papel.
    """
    canal_ifood.config = {
        "payment": {"method": "external", "timing": "external"},
        "fulfillment": {"courier_ticket": "identified"},
    }
    canal_ifood.save(update_fields=["config"])
    order = _pedido_do_ifood("IFOOD-CFG-ERRADA", delivered_by="IFOOD")

    # ⚠️ Não é `caplog`: o `LOGGING` desta casa não propaga `shopman.*` para a
    # raiz, e o handler do caplog vive lá — o aviso saía no stderr e a asserção
    # via lista vazia. Perguntar ao logger do módulo mede o que foi chamado.
    from shopman.shop.services import order_helpers

    with patch.object(order_helpers.logger, "warning") as aviso:
        variante = courier_ticket_variant(order)
    papel = _papel(order)

    assert variante == "anonymous"
    assert "Via do entregador - Anônima" in papel
    assert "Rua das Flores" not in papel
    assert "99911-2233" not in papel
    assert "Ana Ribeiro" not in papel

    assert aviso.call_count == 1, "o piso derrubou a configuração em silêncio"
    registro = aviso.call_args[0][0] % tuple(aviso.call_args[0][1:])
    assert order.ref in registro
    assert "ifood" in registro and "marketplace" in registro
    assert "fulfillment.courier_ticket" in registro


def test_o_piso_tambem_fecha_quando_o_responsavel_e_desconhecido(canal_ifood):
    """Falta de prova não autoriza: desconhecido desce junto com marketplace."""
    canal_ifood.config = {
        "payment": {"method": "external", "timing": "external"},
        "fulfillment": {"courier_ticket": "identified"},
    }
    canal_ifood.save(update_fields=["config"])
    order = _pedido_do_ifood("IFOOD-CFG-DUVIDA", delivered_by=None)

    assert courier_ticket_variant(order) == "anonymous"
    assert "Rua das Flores" not in _papel(order)


def test_o_piso_nao_castiga_a_entrega_que_e_mesmo_da_casa(canal_ifood):
    """⚠️ O piso é sobre logística de TERCEIRO, não sobre a marca do canal.

    Pedido de marketplace que o próprio marketplace mandou a LOJA entregar é
    entrega da casa: se o canal declarar Identificada, o endereço sai — senão o
    entregador contratado pela loja sairia sem saber onde tocar.
    """
    canal_ifood.config = {
        "payment": {"method": "external", "timing": "external"},
        "fulfillment": {"courier_ticket": "identified"},
    }
    canal_ifood.save(update_fields=["config"])
    order = _pedido_do_ifood("IFOOD-CFG-LOJA-ENTREGA", delivered_by="MERCHANT")

    papel = _papel(order)

    assert courier_ticket_variant(order) == "identified"
    assert "Via do entregador - Identificada" in papel
    assert "Rua das Flores, 123 - Apto 42, bloco B" in papel


# ── 2. Via Identificada: o papel leva o que faz a entrega acontecer ───────


def test_entrega_da_casa_imprime_endereco_completo_telefone_e_nome(shop):
    """Sem isto o entregador não sabe em que porta tocar — não há app para consultar."""
    order = _pedido_da_casa("ORD-CASA-2", order_notes="Deixar na portaria, bloco B")

    papel = _papel(order)

    assert "Via do entregador" in papel
    assert "ENTREGAR EM:" in papel
    assert "Rua das Flores, 123 - Apto 42, bloco B" in papel
    assert "Referência: portão azul ao lado da farmácia" in papel
    assert "Cliente: Ana Ribeiro" in papel
    assert "Telefone: (43) 99911-2233" in papel
    assert "Deixar na portaria, bloco B" in papel


def test_entrega_da_casa_com_cobranca_na_porta_diz_quanto_e_quanto_de_troco(shop):
    """O que cobrar e o que levar de troco — a mesma conta da filipeta, um dono só."""
    order = _pedido_da_casa("ORD-CASA-COD", payment={
        "method": "cash",
        "status": "pending",
        "collection": "on_delivery",
        "change_for_q": 5000,
        "tenders": [{"method": "cash", "amount_q": 3600, "collection": "on_delivery",
                     "status": "pending"}],
    })

    papel = _papel(order)

    assert "COBRAR NA ENTREGA" in papel
    assert "Dinheiro" in papel and "R$ 36,00" in papel
    assert "Troco para" in papel and "R$ 50,00" in papel
    assert "Levar de troco" in papel and "R$ 14,00" in papel


def test_pedido_pago_manda_nao_cobrar_nada_em_vez_de_calar(shop):
    """⚠️ Silêncio onde deveria estar o dinheiro é o entregador cobrando à toa."""
    order = _pedido_da_casa("ORD-CASA-PAGO", payment={"method": "pix", "status": "captured"})

    papel = _papel(order)

    assert "Pedido pago. Não cobre nada na entrega." in papel
    assert "COBRAR NA ENTREGA" not in papel


def test_pendente_sem_cobranca_combinada_manda_confirmar_com_a_loja(shop):
    order = _pedido_da_casa("ORD-CASA-LIMBO")

    papel = _papel(order)

    assert "Pagamento pendente e sem cobrança combinada na" in papel
    assert "Confirme com a loja antes de entregar." in papel


# ── 3. Via Anônima: identifica o pedido e para aí ─────────────────────────


def test_entrega_do_ifood_nao_imprime_endereco_nem_telefone(canal_ifood):
    """⚠️ A regra do iFood: documento de parceiro de entrega não traz endereço.

    O entregador já tem tudo na tela do app dele; repetir aqui só espalha dado
    pessoal.
    """
    order = _pedido_do_ifood("IFOOD-SEM-ENDERECO", delivered_by="IFOOD")

    papel = _papel(order)

    assert "Rua das Flores" not in papel
    assert "Apto 42" not in papel
    assert "portão azul" not in papel
    assert "99911-2233" not in papel
    assert "Ana Ribeiro" not in papel
    assert "ENTREGAR EM:" not in papel


def test_a_ausencia_do_endereco_e_dita_em_vez_de_ficar_em_branco(canal_ifood):
    """Espaço vazio faz o leitor adivinhar se a impressora falhou."""
    order = _pedido_do_ifood("IFOOD-DIZ-PORQUE", delivered_by="IFOOD")

    papel = _papel(order)

    assert "QUEM ENTREGA É O IFOOD." in papel
    assert "Endereço, telefone e nome do cliente estão no" in papel
    assert "app do entregador." in papel
    assert "Por privacidade, não saem" in papel


def test_a_via_do_ifood_identifica_o_pedido_sem_ambiguidade(canal_ifood):
    """O que sobra tem de bastar: o número curto do iFood, o ref e o código do balcão."""
    order = _pedido_do_ifood("IFOOD-IDENTIDADE", delivered_by="IFOOD",
                             display_id="8842", pickup_code="4521")

    papel = _papel(order)

    assert "iFood #8842" in papel
    assert f"Pedido {order.ref}" in papel
    assert "Código de retirada no balcão:" in papel
    assert "4521" in papel


def test_a_via_do_ifood_lista_a_sacola_sem_preco(canal_ifood):
    order = _pedido_do_ifood("IFOOD-SACOLA", delivered_by="IFOOD")

    papel = _papel(order)

    assert "CONFIRA A SACOLA - 1 produto" in papel
    assert "1 x Pão francês" in papel
    assert "R$" not in papel


def test_responsavel_desconhecido_manda_confirmar_antes_de_sair(canal_ifood):
    order = _pedido_do_ifood("IFOOD-DUVIDA", delivered_by=None)

    papel = _papel(order)

    assert "O RESPONSÁVEL PELA ENTREGA NÃO FOI INFORMADO" in papel
    assert "PELO IFOOD." in papel
    assert "Confirme com a loja antes de sair." in papel
    assert "Rua das Flores" not in papel


# ── 4. O que NUNCA sai — dos dois lados ───────────────────────────────────


@pytest.mark.parametrize("cenario", ["casa", "ifood"])
def test_cpf_nao_sai_em_nenhuma_via_do_entregador(shop, canal_ifood, cenario):
    """⚠️ O documento do cliente é assunto da NFC-e, que é papel DELE.

    O iFood proíbe CPF em documento de parceiro de entrega, e a casa não tem
    motivo nenhum para imprimi-lo no papel da entrega própria.
    """
    if cenario == "casa":
        # ⚠️ O ``ref`` não carrega as três letras: a asserção varre o papel
        # inteiro em caixa alta, e "ORD-CPF" a faria passar por conta própria.
        order = _pedido_da_casa("ORD-DOC-1", fiscal={"tax_id": "390.533.447-05"})
    else:
        order = _pedido_do_ifood("IFOOD-DOC", delivered_by="MERCHANT")
        assert order.data["fiscal"]["tax_id"] == "390.533.447-05"

    papel = _papel(order)

    assert "390.533.447-05" not in papel
    assert "39053344705" not in papel
    assert "CPF" not in papel.upper()


def test_nenhuma_linha_passa_de_48_colunas(shop):
    """48 colunas foram medidas com régua no papel; estourar é texto perdido."""
    from shopman.backstage.services.receipt_escpos import COLUMNS

    order = _pedido_da_casa(
        "ORD-LARGURA",
        delivery_address="Rua Comendador Alberto Bonfiglioli Sobrinho, 1234, Jardim das Américas",
        order_notes="Por favor entregar depois das dezoito horas porque não tem ninguém em casa antes",
    )
    OrderItem.objects.create(
        order=order, line_id="2", sku="PAO-002",
        name="Pão de fermentação natural com sementes e castanhas do Pará",
        qty=12, unit_price_q=4250, line_total_q=51000,
    )

    limpo = _papel(order).replace("\x1d!\x11", "").replace("\x1d!\x00", "")
    for linha in (bruta.rstrip() for bruta in limpo.split("\n")):
        assert len(linha) <= COLUMNS, f"linha estourou a bobina: {linha!r}"


def _destacado(papel: bytes, texto: str) -> bool:
    """O texto sai em CORPO DUPLO — que é como esta casa destaca desde sempre.

    ``GS ! 0x11`` liga largura e altura dobradas e ``GS ! 0x00`` desliga; o
    destaque é o que está ENTRE os dois. Procurar só a string provaria presença,
    e a norma exige presença **destacada**.
    """
    liga, desliga = bytes([0x1D, ord("!"), 0x11]), bytes([0x1D, ord("!"), 0x00])
    return any(
        texto.encode(ENCODING) in bloco.split(desliga)[0]
        for bloco in papel.split(liga)[1:]
    )


@pytest.mark.parametrize("via", ["identificada", "anonima"])
def test_as_duas_vias_estampam_nao_e_documento_fiscal_em_destaque(canal_proprio, canal_ifood, via):
    """⚠️ Exigência legal, não estética.

    Ajuste SINIEF 19/16, cláusula décima, § 4º (acrescido pelo Ajuste SINIEF
    32/24, efeitos desde 01/02/2025; RICMS/PR art. 31, § 4º): documento não
    fiscal relacionado à NFC-e entregue ao consumidor final deve trazer "NÃO É
    DOCUMENTO FISCAL" de forma DESTACADA e legível.

    As duas vias estampam porque a via viaja com a sacola: não há como garantir
    que ela não chegue à mão do cliente, e carimbo condicionado ao que não se
    controla é carimbo que falta na hora errada.
    """
    order = (
        _pedido_da_casa("ORD-FISCAL")
        if via == "identificada"
        else _pedido_do_ifood("IFOOD-FISCAL", delivered_by="IFOOD")
    )

    bytes_do_papel = courier_ticket(order)
    papel = bytes_do_papel.decode(ENCODING, "replace")

    assert "NÃO É DOCUMENTO FISCAL" in papel
    assert _destacado(bytes_do_papel, "NÃO É DOCUMENTO FISCAL"), "a frase saiu em corpo normal"
    assert "Este papel também não comprova pagamento." in papel


def test_pedido_de_teste_do_ifood_avisa_que_nao_se_entrega_nada(canal_ifood):
    """⚠️ A homologação roda contra o ambiente VIVO, e o papel sai igual.

    Sem a moldura, é alguém saindo de moto para entregar nada.
    """
    order = _pedido_do_ifood("IFOOD-TESTE", delivered_by="MERCHANT", is_test=True)

    papel = _papel(order)

    assert "*** PEDIDO DE TESTE DO IFOOD ***" in papel
    assert "Não entregue nada." in papel


def test_pedido_de_verdade_nao_ganha_cracha_de_teste(canal_ifood):
    order = _pedido_do_ifood("IFOOD-REAL", delivered_by="MERCHANT")

    assert "PEDIDO DE TESTE" not in _papel(order)


# ── 5. A filipeta continua o que era ──────────────────────────────────────


def test_a_via_do_entregador_nao_substitui_a_filipeta(shop):
    """Acrescentar, não trocar: a ficha do painel segue com total e cliente.

    A cozinha e o balcão continuam lendo o papel deles; quem mudou de regra foi
    o papel novo.
    """
    from shopman.backstage.services.receipt_escpos import order_ticket

    order = _pedido_da_casa("ORD-CONVIVEM")

    filipeta = order_ticket(order).decode(ENCODING, "replace")
    assert "Ficha do pedido" in filipeta
    assert "TOTAL R$ 36,00" in filipeta
    assert "Rua das Flores, 123 - Apto 42, bloco B" in filipeta

    via = _papel(order)
    assert "Via do entregador - Identificada" in via
    assert "Ficha do pedido" not in via


# ── 6. A rota, o carimbo de 2ª via e a permissão ──────────────────────────


@pytest.fixture
def gestor(db, shop):
    """Operador do Gestor: staff + ``shop.manage_orders``, NÃO superusuário."""
    user = User.objects.create_user("gestor-via", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"),
            codename="manage_orders",
        )
    )
    return user


def test_a_rota_entrega_os_bytes_e_carimba_a_propria_segunda_via(client, shop, gestor):
    """⚠️ Carimbo PRÓPRIO: a ficha já ter ido para o painel não faz da primeira
    via do entregador uma segunda."""
    import base64

    order = _pedido_da_casa("ORD-ROTA")
    client.force_login(gestor)
    url = reverse("api-backstage-order-courier-ticket-escpos", args=[order.ref])

    primeira = client.get(url)
    assert primeira.status_code == 200
    assert primeira.json()["reprint"] is False
    assert primeira.json()["title"] == f"via-do-entregador:{order.ref}"
    # A resposta DIZ qual via saiu: a tela precisa nomear o papel que o
    # operador pegou, e escolher não é dela.
    assert primeira.json()["variant"] == "identified"
    assert primeira.json()["variant_label"] == "Via do entregador — Identificada"
    papel = base64.b64decode(primeira.json()["payload_b64"]).decode(ENCODING, "replace")
    assert "Via do entregador" in papel
    assert "2a VIA" not in papel

    order.refresh_from_db()
    assert order.data["courier_ticket_printed_at"]
    assert "ticket_printed_at" not in order.data

    segunda = client.get(url)
    assert segunda.json()["reprint"] is True
    assert "2a VIA" in base64.b64decode(segunda.json()["payload_b64"]).decode(ENCODING, "replace")


def test_a_rota_recusa_quem_nao_cuida_da_fila(client, shop, db):
    order = _pedido_da_casa("ORD-SEM-PERMISSAO")
    client.force_login(User.objects.create_user("balconista", password="x"))

    resposta = client.get(reverse("api-backstage-order-courier-ticket-escpos", args=[order.ref]))

    assert resposta.status_code in {403, 404}


def test_o_service_resolve_o_nome_da_loja(shop):
    """``courier_ticket_bytes`` é o par de ``ticket_bytes``: resolve o cabeçalho."""
    Shop.objects.filter(pk=shop.pk).update(name="Nelson Boulangerie")
    order = _pedido_da_casa("ORD-SERVICE")

    papel = tickets.courier_ticket_bytes(order).decode(ENCODING, "replace")

    assert "NELSON BOULANGERIE" in papel
