"""DEV-2026-093 · o link do aviso abre o pedido sem pedir a entrada de novo.

A falha que o dono achou: cliente chegou pelo site, entrou pelo WhatsApp, recebeu os
avisos no WhatsApp e, ao tocar no link do acompanhamento, teve de entrar de novo (o
navegador embutido do WhatsApp não tem a sessão do site). "Tem que ter uma forma de
resolver isso!!!"

O link do aviso leva a capacidade DESTE pedido (``/pedido/<ref>~<selo>``). Estes testes
provam a fronteira dela: abre o pedido e nada mais. Não loga, não lista pedidos, não abre
sacola nem tempo real; não cancela, não pede de novo, não avalia; paga, fala com a loja e
confirma o recebimento; o endereço sai abreviado e o telefone do cliente não aparece. Com
a entrada normal, nada muda.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from shopman.guestman.models import Customer
from shopman.orderman.models import Order

from shopman.shop.adapters import notification_manychat
from shopman.shop.services import order_view_link
from shopman.shop.services.customer_orders import ORDER_ACCESS_SESSION_KEY, ORDER_CAPABILITY_SESSION_KEY
from shopman.storefront.tests.identity_fakes import proven

from .conftest import login_as_customer

pytestmark = pytest.mark.django_db

TELEFONE = "+5543999990931"
DIGITOS_DO_TELEFONE = "999990931"
ENDERECO = "Rua das Flores 123, apto 42 - Centro - Londrina"


@pytest.fixture(autouse=True)
def _sem_portarias_de_ritmo(settings):
    settings.RATELIMIT_ENABLE = False
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def dona(db) -> Customer:
    return proven(Customer.objects.create(ref="CUS-093", first_name="Lia", phone=TELEFONE))


def _pedido(channel, dona, *, ref: str, status: str = "new", **data) -> Order:
    base = {
        "customer_ref": dona.ref,
        "customer": {"ref": dona.ref, "uuid": str(dona.uuid), "name": "Lia", "phone": TELEFONE},
        "fulfillment_type": "delivery",
        "delivery_address": ENDERECO,
        "delivery_address_structured": {
            "route": "Rua das Flores",
            "street_number": "123",
            "complement": "apto 42",
            "neighborhood": "Centro",
            "city": "Londrina",
        },
        "payment": {"method": "pix", "status": "pending", "amount_q": 4200, "copy_paste": "00020126PIX093"},
    }
    base.update(data)
    return Order.objects.create(
        ref=ref,
        channel_ref=channel.ref,
        status=status,
        total_q=4200,
        handle_type="phone",
        handle_ref=TELEFONE,
        data=base,
    )


@pytest.fixture
def pedido(channel, dona) -> Order:
    return _pedido(channel, dona, ref="WEB-261125-A93")


@pytest.fixture
def outro_pedido(channel, dona) -> Order:
    return _pedido(channel, dona, ref="WEB-261125-B93")


def _troca(client: Client, ref: str, cap: str):
    return client.post(f"/api/v1/tracking/{ref}/access/", data={"cap": cap}, content_type="application/json")


def _abre_pelo_link(client: Client, order: Order) -> None:
    resposta = _troca(client, order.ref, order_view_link.capability(order))
    assert resposta.status_code == 200, resposta.content


def _post(client: Client, path: str, body: dict | None = None):
    return client.post(path, data=json.dumps(body or {}), content_type="application/json", HTTP_X_IDEMPOTENCY_KEY="k-093")


# ── A capacidade abre o pedido, e não loga ───────────────────────────────────


def test_o_link_abre_o_pedido_sem_entrar(pedido):
    navegador_do_whatsapp = Client(HTTP_USER_AGENT="Mozilla/5.0 (iPhone) WhatsApp/2.24")
    assert navegador_do_whatsapp.get(f"/api/v1/tracking/{pedido.ref}/").status_code == 404

    _abre_pelo_link(navegador_do_whatsapp, pedido)

    leitura = navegador_do_whatsapp.get(f"/api/v1/tracking/{pedido.ref}/")
    assert leitura.status_code == 200
    assert leitura.json()["ref"] == pedido.ref
    assert leitura.json()["access_mode"] == "capability"


def test_a_capacidade_nao_loga_nem_cria_usuario(pedido, django_user_model):
    usuarios_antes = django_user_model.objects.count()
    cliente = Client()
    _abre_pelo_link(cliente, pedido)

    sessao = cliente.session
    assert "_auth_user_id" not in sessao
    assert sessao.get(ORDER_ACCESS_SESSION_KEY) in (None, []), "acesso pelo link não vira acesso de quem fez o pedido"
    assert sessao[ORDER_CAPABILITY_SESSION_KEY] == {pedido.ref: 0}
    assert django_user_model.objects.count() == usuarios_antes
    assert cliente.get("/api/v1/auth/session/").json()["is_authenticated"] is False


def test_a_capacidade_nao_abre_a_conta_nem_lista_pedidos(pedido):
    cliente = Client()
    _abre_pelo_link(cliente, pedido)

    for caminho in ("/api/v1/account/orders/", "/api/v1/account/summary/",
                    "/api/v1/account/profile/", "/api/v1/account/addresses/"):
        assert cliente.get(caminho).status_code in {401, 403}, caminho
    # O contador do selo da conta não conta o pedido aberto pelo link.
    ativos = cliente.get("/api/v1/account/orders/active/")
    assert ativos.status_code in {200, 401, 403}
    if ativos.status_code == 200:
        assert not any(ativos.json().get(k) for k in ("count", "active_count", "active")), ativos.json()


def test_selo_do_pedido_a_com_ref_do_b_da_404(pedido, outro_pedido):
    cliente = Client()
    assert _troca(cliente, outro_pedido.ref, order_view_link.capability(pedido)).status_code == 404
    assert cliente.get(f"/api/v1/tracking/{outro_pedido.ref}/").status_code == 404

    # Aberto o A, o B continua fechado.
    _abre_pelo_link(cliente, pedido)
    assert cliente.get(f"/api/v1/tracking/{outro_pedido.ref}/").status_code == 404


def test_selo_adulterado_da_404(pedido):
    cap = order_view_link.capability(pedido)
    adulterado = ("A" if cap[0] != "A" else "B") + cap[1:]
    cliente = Client()
    for selo in (adulterado, cap[:-1], "", "x" * 22):
        assert _troca(cliente, pedido.ref, selo).status_code == 404, selo
    assert _troca(cliente, "NAO-EXISTE", cap).status_code == 404
    assert cliente.get(f"/api/v1/tracking/{pedido.ref}/").status_code == 404


def test_selo_vencido_oito_dias_depois_de_concluido_da_404(channel, dona):
    agora = timezone.now()
    vencido = _pedido(channel, dona, ref="WEB-261117-C93", status="completed")
    Order.objects.filter(pk=vencido.pk).update(completed_at=agora - timedelta(days=8))
    vencido.refresh_from_db()
    assert _troca(Client(), vencido.ref, order_view_link.capability(vencido)).status_code == 404

    valendo = _pedido(channel, dona, ref="WEB-261119-D93", status="completed")
    Order.objects.filter(pk=valendo.pk).update(completed_at=agora - timedelta(days=6))
    valendo.refresh_from_db()
    cliente = Client()
    _abre_pelo_link(cliente, valendo)
    assert cliente.get(f"/api/v1/tracking/{valendo.ref}/").status_code == 200

    # Passou da validade depois da troca: a leitura fecha também.
    Order.objects.filter(pk=valendo.pk).update(completed_at=agora - timedelta(days=8))
    assert cliente.get(f"/api/v1/tracking/{valendo.ref}/").status_code == 404


def test_selo_vencido_de_pedido_cancelado_da_404(channel, dona):
    cancelado = _pedido(channel, dona, ref="WEB-261117-E93", status="cancelled")
    Order.objects.filter(pk=cancelado.pk).update(cancelled_at=timezone.now() - timedelta(days=8))
    cancelado.refresh_from_db()
    assert _troca(Client(), cancelado.ref, order_view_link.capability(cancelado)).status_code == 404


def test_selo_revogado_da_404_ate_para_quem_ja_tinha_trocado(pedido):
    selo_antigo = order_view_link.capability(pedido)
    cliente = Client()
    _abre_pelo_link(cliente, pedido)

    assert order_view_link.revoke(pedido) == 1
    pedido.refresh_from_db()
    assert pedido.data[order_view_link.REV_KEY] == 1

    assert cliente.get(f"/api/v1/tracking/{pedido.ref}/").status_code == 404
    assert _troca(Client(), pedido.ref, selo_antigo).status_code == 404
    # O selo novo abre.
    _abre_pelo_link(Client(), pedido)


def test_capacidade_nao_abre_tempo_real_nem_sacola(pedido, product):
    cliente = Client()
    _abre_pelo_link(cliente, pedido)

    assert cliente.get(f"/api/v1/tracking/{pedido.ref}/events/").status_code == 404
    recompra = _post(cliente, f"/api/v1/orders/{pedido.ref}/reorder/", {"mode": "replace"})
    assert recompra.status_code == 403
    assert "cart_session_key" not in cliente.session, "o link do aviso não cria sacola"


# ── O que o link faz e o que pede a entrada ──────────────────────────────────


def test_cancelar_so_com_a_capacidade_recusa_com_convite_para_entrar(pedido):
    cliente = Client()
    _abre_pelo_link(cliente, pedido)

    resposta = _post(cliente, f"/api/v1/orders/{pedido.ref}/cancel/")
    assert resposta.status_code == 403
    corpo = resposta.json()
    assert corpo["error_code"] == "login_required"
    assert corpo["detail"]
    assert corpo["login_url"] == f"/entrar?next=%2Fpedido%2F{pedido.ref}"
    assert corpo["actions"][0]["href"] == corpo["login_url"]
    pedido.refresh_from_db()
    assert pedido.status == "new"


def test_avaliar_e_pedir_de_novo_so_com_a_capacidade_recusam(channel, dona):
    concluido = _pedido(channel, dona, ref="WEB-261124-F93", status="completed")
    Order.objects.filter(pk=concluido.pk).update(completed_at=timezone.now())
    cliente = Client()
    _abre_pelo_link(cliente, concluido)

    avaliar = _post(cliente, f"/api/v1/orders/{concluido.ref}/rate/", {"rating": 5})
    assert avaliar.status_code == 403
    assert avaliar.json()["error_code"] == "login_required"
    recompra = _post(cliente, f"/api/v1/orders/{concluido.ref}/reorder/", {"mode": "replace"})
    assert recompra.status_code == 403
    assert recompra.json()["error_code"] == "login_required"
    concluido.refresh_from_db()
    assert "customer_rating" not in concluido.data


def test_confirmar_a_vaga_da_fila_so_com_a_capacidade_recusa(pedido):
    cliente = Client()
    _abre_pelo_link(cliente, pedido)
    resposta = _post(cliente, f"/api/v1/orders/{pedido.ref}/waitlist-confirm/")
    assert resposta.status_code == 403
    assert resposta.json()["error_code"] == "login_required"


def test_a_tela_aberta_pelo_link_nao_oferece_cancelar_e_convida_a_entrar(pedido):
    cliente = Client()
    _abre_pelo_link(cliente, pedido)
    dados = cliente.get(f"/api/v1/tracking/{pedido.ref}/").json()

    refs = {acao["ref"] for acao in dados["actions"]} | {acao["ref"] for acao in dados["promise"]["actions"]}
    assert not refs & {"cancel_order", "reorder", "rate_order"}
    assert dados["login_invite"]["href"] == f"/entrar?next=%2Fpedido%2F{pedido.ref}"
    assert "cancelar" in dados["login_invite"]["message"]


def test_pagar_o_pix_funciona_com_a_capacidade(pedido):
    cliente = Client()
    _abre_pelo_link(cliente, pedido)
    resposta = _post(cliente, f"/api/v1/orders/{pedido.ref}/payment/check/")
    assert resposta.status_code == 200
    assert resposta.json()["access_mode"] == "capability"


def test_falar_com_a_loja_funciona_com_a_capacidade(channel, dona):
    em_preparo = _pedido(channel, dona, ref="WEB-261125-G93", status="preparing")
    cliente = Client()
    _abre_pelo_link(cliente, em_preparo)
    resposta = _post(cliente, f"/api/v1/orders/{em_preparo.ref}/contact-request/", {"origin": "cancellation"})
    assert resposta.status_code == 200, resposta.content


def test_confirmar_recebimento_funciona_com_a_capacidade(channel, dona):
    saiu = _pedido(channel, dona, ref="WEB-261125-H93", status="dispatched")
    cliente = Client()
    _abre_pelo_link(cliente, saiu)
    resposta = _post(cliente, f"/api/v1/orders/{saiu.ref}/confirm-received/")
    assert resposta.status_code == 200, resposta.content
    saiu.refresh_from_db()
    assert saiu.status == "delivered"


# ── O que a tela mostra ──────────────────────────────────────────────────────


def test_endereco_abreviado_e_telefone_fora_so_no_acesso_pela_capacidade(pedido, dona):
    pelo_link = Client()
    _abre_pelo_link(pelo_link, pedido)
    capacidade = pelo_link.get(f"/api/v1/tracking/{pedido.ref}/")
    assert capacidade.json()["delivery_address"] == "Rua das Flores, Centro"
    bruto = capacidade.content.decode()
    for dado in ("Flores 123", "123,", "apto 42", DIGITOS_DO_TELEFONE):
        assert dado not in bruto, dado

    logada = Client()
    login_as_customer(logada, dona)
    completo = logada.get(f"/api/v1/tracking/{pedido.ref}/").json()
    assert completo["access_mode"] == "full"
    assert completo["delivery_address"] == ENDERECO
    assert completo["login_invite"] is None


# ── Com a entrada normal, nada muda ──────────────────────────────────────────


def test_com_login_cancelar_segue_funcionando(pedido, dona):
    logada = Client()
    login_as_customer(logada, dona)
    # Ter trocado o selo antes não rebaixa quem entrou.
    _abre_pelo_link(logada, pedido)

    dados = logada.get(f"/api/v1/tracking/{pedido.ref}/").json()
    assert dados["access_mode"] == "full"
    assert "cancel_order" in {acao["ref"] for acao in dados["actions"]}

    resposta = _post(logada, f"/api/v1/orders/{pedido.ref}/cancel/")
    assert resposta.status_code == 200, resposta.content
    pedido.refresh_from_db()
    assert pedido.status == "cancelled"


def test_o_navegador_do_checkout_segue_com_acesso_completo(pedido):
    checkout = Client()
    sessao = checkout.session
    sessao[ORDER_ACCESS_SESSION_KEY] = [pedido.ref]
    sessao.save()
    dados = checkout.get(f"/api/v1/tracking/{pedido.ref}/").json()
    assert dados["access_mode"] == "full"
    assert dados["delivery_address"] == ENDERECO


# ── ManyChat: o campo do botão leva o ref com o selo ─────────────────────────


def test_manychat_grava_o_ref_com_o_selo_no_campo_do_botao_e_recusa_link_de_entrada(pedido):
    from shopman.shop.services import notification as notification_service

    contexto = notification_service._build_context(pedido, {"order_ref": pedido.ref}, "order_dispatched")
    campos = notification_manychat._shareable_context(contexto)

    assert campos["order_ref"] == order_view_link.link_ref(pedido)
    assert "order_link_ref" not in campos
    assert campos["tracking_url"].endswith(f"/pedido/{order_view_link.link_ref(pedido)}")

    com_token = dict(contexto, action_url="https://loja.test/a?t=SEGREDO")
    assert "action_url" not in notification_manychat._shareable_context(com_token)
