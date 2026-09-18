"""Duas espécies de estação: a atendida e a autônoma.

O balcão tem gente na frente e não faz nada sem PIN. O painel de parede da
Produção não tem — e por isso age em NOME PRÓPRIO, com uma conta que é dele. As
duas dividem a mesma regra: o DISPOSITIVO não concede nada; quem concede é a
identidade.

⚠️ **E a autônoma só vale na Produção.** Esta é a metade do arquivo que importa,
e ela é sobre o COOKIE, não sobre o produto. O cookie de confiança de estação é
nomeado por terminal, mas o domínio dele é ``.boulangerie.com.br`` inteiro
(``SHOPMAN_OPERATOR_COOKIE_DOMAIN``): o mesmo tablet que é kiosk de Produção, ao
abrir ``pdv.boulangerie.com.br``, leva a confiança junto. Sem uma trava de
SUPERFÍCIE do lado do servidor, ``_operador()`` resolveria a conta do totem lá
também e daria as permissões dela no balcão — a forma exata do buraco de 20/08
que o ``station_trust`` existe para fechar.

Por isso os testes que provam este arquivo são os NEGATIVOS: o que o cookie do
totem NÃO faz fora da Produção.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.cashman.models import Shift, Terminal

from shopman.backstage import station_trust
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Shop

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("_loja")]

POS_URL = "/api/v1/backstage/pos/"
KDS_URL = "/api/v1/backstage/kds/"
ORDERS_URL = "/api/v1/backstage/orders/"
SESSION_URL = "/api/v1/backstage/operator/session/"

#: A superfície onde a estação autônoma age. Tudo que é positivo neste arquivo
#: passa por aqui; tudo que é negativo passa por fora.
PRODUCTION_URL = "/api/v1/backstage/production/"
PRODUCTION_SESSION_URL = "/api/v1/backstage/production/session/"


@pytest.fixture
def _loja():
    return Shop.objects.create(name="Nelson", brand_name="Nelson")


def _grant(user, codename: str):
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))
    return get_user_model().objects.get(pk=user.pk)


def _backstage_perm(codename: str) -> Permission:
    from shopman.backstage.models import DayClosing

    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename=codename,
    )


def _grant_production(user):
    """O que a loja concede ao painel: entrar na superfície de Produção."""
    user.user_permissions.add(_backstage_perm("operate_production"))
    return get_user_model().objects.get(pk=user.pk)


def _terminal(ref: str, *, mode: str, operator: str = "") -> Terminal:
    bloco = {"mode": mode}
    if operator:
        bloco["operator"] = operator
    return Terminal.objects.create(ref=ref, label=ref, metadata={"station": bloco})


def _conta_do_totem(username: str = "totem-entrada", **extra):
    user = get_user_model().objects.create_user(username, password="x", is_staff=True, **extra)
    return get_user_model().objects.get(pk=user.pk)


def _totem_pronto(ref: str = "totem-1", username: str = "totem-entrada"):
    """Uma estação autônoma COMPLETA: declarada, com conta e com permissão.

    Os negativos usam isto de propósito. Um negativo montado sobre config
    quebrada provaria a config, não a trava — e passaria verde mesmo se a trava
    de superfície fosse apagada amanhã.
    """
    terminal = _terminal(ref, mode=station_trust.AUTONOMOUS, operator=username)
    conta = _grant_production(_conta_do_totem(username))
    _grant(conta, "operate_pos")  # o balcão inteiro, de propósito — ver os negativos
    return terminal, get_user_model().objects.get(pk=conta.pk)


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
    """Config inválida não pode promover um painel a dispositivo que age sozinho."""
    _terminal("painel", mode="autonoma", operator="totem-entrada")  # não é `autonomous`
    _grant_production(_conta_do_totem())
    trust_station(client, "painel")

    resposta = client.get(PRODUCTION_SESSION_URL)

    assert resposta.status_code == 200
    assert resposta.json()["locked"] is True


# ── A autônoma, na Produção ──────────────────────────────────────────────────


def test_a_estacao_AUTONOMA_age_em_nome_da_PROPRIA_conta(client):
    _totem_pronto()
    trust_station(client, "totem-1")

    assert client.get(PRODUCTION_URL).status_code == 200
    # E a tela sabe quem ela é: a antessala da Produção não a reporta travada,
    # porque não há ninguém para destravá-la.
    sessao = client.get(PRODUCTION_SESSION_URL).json()
    assert sessao["locked"] is False
    assert sessao["operator"]["username"] == "totem-entrada"
    assert sessao["station"] == "totem-1"


def test_a_conta_do_totem_so_pode_o_que_lhe_concederam(client):
    """Ser o dispositivo não dá permissão nenhuma — nem dentro da Produção.

    Sem concessão, a recusa é a comum (capacidade que falta), não
    `station_locked`: PIN não resolveria, porque não há quem digite.
    """
    _terminal("totem-1", mode=station_trust.AUTONOMOUS, operator="totem-entrada")
    _conta_do_totem()  # nenhuma permissão concedida
    trust_station(client, "totem-1")

    resposta = client.get(PRODUCTION_URL)

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "forbidden"


def test_totem_SUPERUSUARIO_e_recusado(client):
    """O buraco de 20/08 com outro nome: um dispositivo com chave-mestra.

    `is_superuser` curto-circuita `has_perm`, então uma conta dessas ignoraria
    qualquer conjunto mínimo que a loja tentasse declarar. A recusa é dura de
    propósito — o painel volta a ser um dispositivo sem identidade.
    """
    _terminal("totem-1", mode=station_trust.AUTONOMOUS, operator="totem-root")
    get_user_model().objects.create_superuser("totem-root", password="x")
    trust_station(client, "totem-1")

    resposta = client.get(PRODUCTION_URL)

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

    resposta = client.get(PRODUCTION_URL)

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "station_locked"


def test_desativar_a_conta_DESLIGA_o_totem(client):
    """É como se desliga um painel sem ir até ele — e tem de bastar."""
    _, conta = _totem_pronto()
    trust_station(client, "totem-1")
    assert client.get(PRODUCTION_URL).status_code == 200

    conta.is_active = False
    conta.save(update_fields=["is_active"])

    assert client.get(PRODUCTION_URL).status_code == 403
    assert client.get(PRODUCTION_SESSION_URL).json()["locked"] is True


def test_a_confianca_de_um_totem_nao_serve_para_o_balcao_do_lado(client):
    """Cada dispositivo carrega o cookie do SEU ref; um não empresta identidade ao outro."""
    _totem_pronto()
    _terminal("balcao", mode=station_trust.ATTENDED)
    trust_station(client, "balcao")

    resposta = client.get(PRODUCTION_URL)

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "station_locked"


def test_a_requisicao_da_producao_tem_o_totem_como_ATOR(client, rf):
    """Agir em nome próprio vale também para a trilha: o que ele faz tem dono.

    `request.user` É a conta do totem — não um segundo sujeito ao lado dela —
    então a atribuição (`_actor`, `Entry.operator`) sai certa de graça em todo
    caminho de Produção, sem que nenhum deles precise conhecer a estação.
    """
    from shopman.backstage.api.permissions import _operador

    _, conta = _totem_pronto()
    requisicao = rf.get(PRODUCTION_URL)
    requisicao.COOKIES[station_trust.station_cookie_name("totem-1")] = _token("totem-1")

    ator = _operador(requisicao)

    assert ator is not None and ator.pk == conta.pk
    assert requisicao.user.pk == conta.pk


def _token(terminal_ref: str) -> str:
    from shopman.doorman.models import SubjectType, TrustedDevice

    _, raw = TrustedDevice.create_for(
        subject_type=SubjectType.STATION,
        subject_id=terminal_ref,
        user_agent="teste",
        ip_address="127.0.0.1",
    )
    return raw


# ── Os NEGATIVOS: onde o cookie do totem não vale nada ───────────────────────
#
# Cada um destes monta uma estação autônoma PERFEITA — declarada, com conta
# válida, e com a permissão que a superfície do teste pede — e prova que ela
# mesmo assim não age. Se a trava de superfície sumir, eles ficam vermelhos.


def test_o_cookie_do_totem_NAO_vira_operador_no_PDV(client):
    """O caso que a trava existe para impedir: o mesmo aparelho, na aba do PDV.

    A conta deste teste TEM `cashman.operate_pos`. É o pior caso de propósito:
    sem a trava de superfície o balcão abriria inteiro, sem PIN e sem ninguém.
    """
    _totem_pronto()
    trust_station(client, "totem-1")

    resposta = client.get(POS_URL)

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "station_locked"


def test_o_cookie_do_totem_NAO_abre_caixa(client):
    """Dinheiro é o teste de fogo: a recusa vale para a escrita, não só a leitura."""
    terminal, _ = _totem_pronto()
    trust_station(client, "totem-1")

    abrir = client.post(
        reverse("api-backstage-pos-cash-open"),
        {"opening_amount": "100,00", "terminal_ref": terminal.ref},
        content_type="application/json",
    )

    assert abrir.status_code == 403
    assert not Shift.objects.exists()


def test_o_cookie_do_totem_NAO_vira_operador_no_KDS(client):
    """O KDS tem gente na frente; lá o caminho é o atendido, com PIN."""
    _totem_pronto()
    _grant_kds(get_user_model().objects.get(username="totem-entrada"))
    trust_station(client, "totem-1")

    resposta = client.get(KDS_URL)

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "station_locked"


def _grant_kds(user):
    from shopman.backstage.models import KDSTicket

    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get_for_model(KDSTicket),
            codename="operate_kds",
        )
    )
    return get_user_model().objects.get(pk=user.pk)


def test_o_cookie_do_totem_NAO_vira_operador_no_gestor_de_pedidos(client):
    """Qualquer rota fora da Produção, não só as três superfícies conhecidas."""
    _totem_pronto()
    conta = get_user_model().objects.get(username="totem-entrada")
    conta.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"),
            codename="manage_orders",
        )
    )
    trust_station(client, "totem-1")

    resposta = client.get(ORDERS_URL)

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "station_locked"


def test_a_antessala_COMPARTILHADA_reporta_o_totem_como_travado(client):
    """`operator/session/` é de todas as superfícies — e por isso fica de fora.

    Se ela resolvesse o totem, o PDV com o mesmo cookie leria `locked: false`
    com o nome do painel: a pessoa no balcão perderia a tela de PIN e ficaria
    olhando um PDV que recusa toda leitura. A antessala da Produção mora sob o
    prefixo da Produção — ver `api-backstage-production-session`.
    """
    _totem_pronto()
    trust_station(client, "totem-1")

    sessao = client.get(SESSION_URL).json()

    assert sessao["locked"] is True
    assert sessao["operator"] is None
    # A estação continua RECONHECIDA: o balcão sabe de que terminal é, e por isso
    # tem como pedir PIN. Perder isso trancaria o aparelho para a pessoa também.
    assert sessao["station"] == "totem-1"


# ── A trava é o PREFIXO, e o prefixo não pode derivar ────────────────────────


def test_o_prefixo_da_trava_e_o_MESMO_que_o_roteador_usa():
    """A constante sai do `urls.py`, ou a trava viraria uma string decorativa.

    Mover a Produção de caminho e esquecer desta linha teria dois sintomas, os
    dois calados: o painel parando de agir, ou — pior — o prefixo antigo passando
    a cobrir uma rota que não é de Produção.
    """
    assert station_trust.PRODUCTION_API_PREFIX == reverse("api-backstage-production")


@pytest.mark.parametrize(
    "nome",
    [
        "api-backstage-pos",
        "api-backstage-kds-index",
        "api-backstage-orders",
        "api-backstage-operator-session",
        "api-backstage-operator-unlock",
        # ⚠️ O quase-acerto: `bi/production/` tem "production" no caminho e NÃO é a
        # superfície de Produção — é o B.I., persona gestor. Uma trava escrita com
        # `"production" in path` teria dado a ele a conta do painel.
        "api-backstage-bi-production",
    ],
)
def test_rota_que_NAO_e_da_producao_fica_fora_do_prefixo(nome):
    assert not reverse(nome).startswith(station_trust.PRODUCTION_API_PREFIX)


@pytest.mark.parametrize(
    "nome",
    [
        "api-backstage-production",
        "api-backstage-production-session",
        "api-backstage-production-kds",
        "api-backstage-production-weighing",
        "api-backstage-wo-plan",
        "api-backstage-wo-quick-finish",
    ],
)
def test_rota_da_producao_fica_DENTRO_do_prefixo(nome):
    assert reverse(nome).startswith(station_trust.PRODUCTION_API_PREFIX)


def test_a_trava_nao_acredita_no_que_o_cliente_diz_de_si(rf):
    """Nada que o navegador afirme sobre si mesmo entra nesta decisão.

    Host, Referer, Origin e um cabeçalho de superfície são todos escritos pelo
    cliente. Quem responde é o caminho — a mesma string que escolheu a view.
    """
    mentira = rf.get(
        POS_URL,
        HTTP_HOST="prod.boulangerie.com.br",
        HTTP_REFERER="https://prod.boulangerie.com.br/board",
        HTTP_X_SHOPMAN_SURFACE="production",
    )

    assert station_trust.is_production_surface(mentira) is False
    assert station_trust.is_production_surface(rf.get(PRODUCTION_URL)) is True


def test_requisicao_sem_caminho_cai_do_lado_SEGURO():
    """Superfície que não se reconhece = atendida. Falha fechado, sempre."""

    class _SemCaminho:
        pass

    assert station_trust.is_production_surface(_SemCaminho()) is False
