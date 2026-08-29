"""Duas espécies de estação: a atendida e a autônoma.

O balcão tem gente na frente e não faz nada sem PIN. O totem não tem — e por isso
age em NOME PRÓPRIO, com uma conta que é dele. As duas dividem a mesma regra: o
DISPOSITIVO não concede nada; quem concede é a identidade.

⚠️ A superfície do totem ainda não existe, e este arquivo não a inventa. O que se
prova aqui é só a camada de identidade — que é o que precisa estar certo ANTES,
porque é ela que ficaria cara de mudar depois. Quando o totem chegar (Stone
AutoTEF ou o que for), o deployment cria a conta, concede o que aquela superfície
precisa, e vira o modo do terminal. Nada de identidade se redesenha.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from shopman.cashman.models import Shift, Terminal

from shopman.backstage import station_trust
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Shop

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("_loja")]

POS_URL = "/api/v1/backstage/pos/"
SESSION_URL = "/api/v1/backstage/operator/session/"


@pytest.fixture
def _loja():
    return Shop.objects.create(name="Nelson", brand_name="Nelson")


def _grant(user, codename: str):
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))
    return get_user_model().objects.get(pk=user.pk)


def _terminal(ref: str, *, mode: str, operator: str = "") -> Terminal:
    bloco = {"mode": mode}
    if operator:
        bloco["operator"] = operator
    return Terminal.objects.create(ref=ref, label=ref, metadata={"station": bloco})


def _conta_do_totem(username: str = "totem-entrada", **extra):
    user = get_user_model().objects.create_user(username, password="x", is_staff=True, **extra)
    return get_user_model().objects.get(pk=user.pk)


# ── A atendida ───────────────────────────────────────────────────────────────


def test_a_estacao_ATENDIDA_nao_faz_nada_sem_PIN(client):
    _terminal("balcao", mode=station_trust.ATTENDED)
    trust_station(client, "balcao")

    resposta = client.get(POS_URL)

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "station_locked"


def test_terminal_sem_bloco_de_estacao_e_ATENDIDO(client):
    """O default fecha a porta: quem não declarou nada continua pedindo PIN."""
    Terminal.objects.create(ref="balcao", label="Balcão")
    trust_station(client, "balcao")

    assert client.get(POS_URL).status_code == 403


def test_modo_escrito_errado_cai_em_ATENDIDA(client):
    """Config inválida não pode promover um balcão a dispositivo que age sozinho."""
    _terminal("balcao", mode="autonoma", operator="totem-entrada")  # não é `autonomous`
    _grant(_conta_do_totem(), "operate_pos")
    trust_station(client, "balcao")

    assert client.get(POS_URL).status_code == 403


# ── A autônoma ───────────────────────────────────────────────────────────────


def test_a_estacao_AUTONOMA_age_em_nome_da_PROPRIA_conta(client):
    _terminal("totem-1", mode=station_trust.AUTONOMOUS, operator="totem-entrada")
    _grant(_conta_do_totem(), "operate_pos")
    trust_station(client, "totem-1")

    resposta = client.get(POS_URL)

    assert resposta.status_code == 200
    # E a tela sabe quem ela é: a antessala não a reporta travada, porque não há
    # ninguém para destravá-la.
    sessao = client.get(SESSION_URL).json()
    assert sessao["locked"] is False
    assert sessao["operator"]["username"] == "totem-entrada"
    assert sessao["station"] == "totem-1"


def test_a_conta_do_totem_so_pode_o_que_lhe_concederam(client):
    """O conjunto mínimo é DADO, não código — e sem concessão o totem não faz nada.

    É a diferença que separa este desenho do anterior: ser o dispositivo não dá
    permissão nenhuma. Enquanto a superfície do totem não existir, a conta dele
    não precisa de permissão alguma, e o gate a trata como qualquer operador sem
    permissão — recusa comum, não `station_locked`, porque PIN não resolveria.
    """
    _terminal("totem-1", mode=station_trust.AUTONOMOUS, operator="totem-entrada")
    _conta_do_totem()  # nenhuma permissão concedida
    trust_station(client, "totem-1")

    resposta = client.get(POS_URL)

    assert resposta.status_code == 403
    corpo = resposta.json()
    assert "error" not in corpo
    # E a recusa diz a VERDADE. O totem opera sem sessão (não há quem digite
    # PIN), então enquanto o gate devolvia False o DRF trocava a recusa por
    # `NotAuthenticated` e o totem identificado ouvia "as credenciais não foram
    # fornecidas" — mensagem errada, e um caminho que não leva a lugar nenhum,
    # porque este dispositivo não tem login a oferecer.
    assert corpo["detail"] == "Operador sem permissão para esta ação."


def test_totem_SUPERUSUARIO_e_recusado(client):
    """O buraco de 20/08 com outro nome: um dispositivo com chave-mestra.

    `is_superuser` curto-circuita `has_perm`, então uma conta dessas ignoraria
    qualquer conjunto mínimo que a loja tentasse declarar. A recusa é dura de
    propósito — o totem volta a ser um dispositivo sem identidade.
    """
    _terminal("totem-1", mode=station_trust.AUTONOMOUS, operator="totem-root")
    get_user_model().objects.create_superuser("totem-root", password="x")
    trust_station(client, "totem-1")

    resposta = client.get(POS_URL)

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "station_locked"


@pytest.mark.parametrize(
    "quebra",
    [
        pytest.param({"operator": ""}, id="sem-conta-declarada"),
        pytest.param({"operator": "quem-nao-existe"}, id="conta-inexistente"),
    ],
)
def test_autonoma_mal_declarada_volta_a_pedir_PIN(client, quebra):
    """Falha fechada: sem uma conta resolvível, sobra a antessala."""
    _terminal("totem-1", mode=station_trust.AUTONOMOUS, **quebra)
    trust_station(client, "totem-1")

    resposta = client.get(POS_URL)

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "station_locked"


def test_desativar_a_conta_DESLIGA_o_totem(client):
    """É como se desliga um totem sem ir até ele — e tem de bastar."""
    _terminal("totem-1", mode=station_trust.AUTONOMOUS, operator="totem-entrada")
    conta = _grant(_conta_do_totem(), "operate_pos")
    trust_station(client, "totem-1")
    assert client.get(POS_URL).status_code == 200

    conta.is_active = False
    conta.save(update_fields=["is_active"])

    assert client.get(POS_URL).status_code == 403


def test_a_confianca_de_um_totem_nao_serve_para_o_balcao_do_lado(client):
    """Cada dispositivo carrega o cookie do SEU ref; um não empresta identidade ao outro."""
    _terminal("totem-1", mode=station_trust.AUTONOMOUS, operator="totem-entrada")
    _terminal("balcao", mode=station_trust.ATTENDED)
    _grant(_conta_do_totem(), "operate_pos")
    trust_station(client, "balcao")

    resposta = client.get(POS_URL)

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "station_locked"


def test_a_trilha_sai_no_nome_do_TOTEM(client):
    """Agir em nome próprio vale também para a trilha: o que ele faz tem dono.

    Sem isto, "age em nome próprio" seria só uma permissão a mais, e a linha
    sairia órfã — o mesmo defeito que a Parte B existe para fechar, com um
    dispositivo no lugar do ``admin``.

    O caminho aqui é um pedido, não a gaveta: abrir pedido é o que o dono disse
    que o totem faz. A gaveta segue exigindo ``cashman.operate_pos``, que a conta
    deste teste não tem.
    """
    from django.urls import reverse
    from shopman.orderman.models import Order, OrderItem

    _terminal("totem-1", mode=station_trust.AUTONOMOUS, operator="totem-entrada")
    conta = _conta_do_totem()
    conta.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"),
            codename="manage_orders",
        )
    )
    conta = get_user_model().objects.get(pk=conta.pk)
    pedido = Order.objects.create(
        ref="ORD-TOTEM-1", channel_ref="totem", status="accepted", total_q=1500,
        data={"customer": {"name": "Ana"}, "payment": {"method": "pix"}},
    )
    OrderItem.objects.create(
        order=pedido, line_id="1", sku="SKU", name="Pão", qty=1,
        unit_price_q=1500, line_total_q=1500,
    )
    trust_station(client, "totem-1")

    resposta = client.post(
        reverse("api-backstage-order-comment", args=[pedido.ref]),
        {"note": "Retirada pelo totem"},
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    detalhe = client.get(reverse("api-backstage-order-detail", args=[pedido.ref])).json()["order"]
    comentarios = [e for e in detalhe["timeline"] if e["event_type"] == "operator_comment"]
    assert comentarios, "o comentário não entrou na linha do tempo"
    assert conta.username in str(comentarios[0])


def test_a_gaveta_continua_fora_do_alcance_do_totem(client):
    """"Nada de gaveta": a conta do totem não tem `operate_pos`, e o gate basta.

    Não foi preciso inventar regra nova para isto — é a mesma pergunta que o gate
    faz a qualquer operador. É por isso que o conjunto mínimo pode ser decidido
    depois, quando a superfície do totem existir, sem mexer na identidade.
    """
    from django.urls import reverse

    terminal = _terminal("totem-1", mode=station_trust.AUTONOMOUS, operator="totem-entrada")
    _conta_do_totem()
    trust_station(client, "totem-1")

    abrir = client.post(
        reverse("api-backstage-pos-cash-open"),
        {"opening_amount": "100,00", "terminal_ref": terminal.ref},
        content_type="application/json",
    )

    assert abrir.status_code == 403
    assert not Shift.objects.exists()
