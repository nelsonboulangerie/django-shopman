"""Como um dispositivo VIRA uma estação — e por que isso não pode ser fácil demais.

Sem este caminho nada do resto existe: o gate da estação é a chave da antessala,
e isto é quem entrega a chave. Um dispositivo não provisionado não tem antessala, o
balcão amanhece pedindo senha de gestor, e a loja não abre com PIN.

O ato é de gestão e acontece uma vez por dispositivo: alguém com
``cashman.manage_operators`` entra com senha ali e diz "este computador é o
pdv-main". Depois disso, o cookie responde por ele.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from shopman.cashman.models import Shift, Terminal
from shopman.doorman.models import SubjectType, TrustedDevice

from shopman.backstage import station_trust
from shopman.backstage.tests.support import trust_station
from shopman.shop.models import Shop

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("_loja")]

STATION_URL = "/api/v1/backstage/operator/station/"
POS_URL = "/api/v1/backstage/pos/"


@pytest.fixture
def _loja():
    return Shop.objects.create(name="Nelson", brand_name="Nelson")


def _grant(user, *codenames):
    ct = ContentType.objects.get_for_model(Shift)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))
    return get_user_model().objects.get(pk=user.pk)


@pytest.fixture
def terminal():
    return Terminal.objects.create(ref="pdv-main", label="PDV principal")


@pytest.fixture
def gerente(terminal):
    user = get_user_model().objects.create_user("marina", password="x", is_staff=True)
    return _grant(user, "manage_operators", "operate_pos")


def test_o_gerente_transforma_o_dispositivo_em_estacao(client, gerente, terminal):
    """O caminho da montagem do balcão, inteiro."""
    client.force_login(gerente)

    resposta = client.post(
        STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json"
    )

    assert resposta.status_code == 200
    assert resposta.json()["station"] == terminal.ref
    assert TrustedDevice.objects.filter(
        subject_type=SubjectType.STATION, subject_id=terminal.ref, is_active=True
    ).count() == 1
    # E o navegador saiu daqui com a chave: a antessala já o reconhece.
    sessao = client.get(reverse("api-backstage-operator-session")).json()
    assert sessao["station"] == terminal.ref


def test_a_estacao_e_a_sessao_do_gestor_sobrevivem_ao_lock(client, gerente, terminal):
    """O ponto inteiro: provisionar uma vez e travar só a superfície do balcão.

    A confiança da estação e a sessão compartilhada do Gestor não podem morrer
    quando o PDV é travado; apenas a capability do PDV volta à antessala.
    """
    client.force_login(gerente)
    client.post(STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json")

    client.post(
        reverse("api-backstage-operator-lock"),
        {"perm": "cashman.operate_pos"},
        content_type="application/json",
    )

    sessao = client.get(
        reverse("api-backstage-operator-session"),
        {"perm": "cashman.operate_pos"},
    ).json()
    assert sessao["locked"] is True
    assert sessao["operator"]["username"] == "marina"
    assert sessao["station"] == terminal.ref
    # ...e apenas a superfície travada deixa de autorizar ações.
    assert client.get(POS_URL).status_code == 403


def test_quem_nao_gere_operadores_nao_provisiona(client, terminal):
    """Provisionar é decidir que aquele dispositivo passa a pedir identificação.

    Um operador de caixa que pudesse fazê-lo transformaria o próprio celular numa
    estação da loja — e a chave da antessala sairia pela porta no fim do turno.
    """
    caixa = _grant(
        get_user_model().objects.create_user("joyce", password="x", is_staff=True), "operate_pos"
    )
    client.force_login(caixa)

    resposta = client.post(
        STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json"
    )

    assert resposta.status_code == 403
    assert not TrustedDevice.objects.filter(subject_type=SubjectType.STATION).exists()


def test_terminal_desconhecido_e_recusado(client, gerente):
    """Confiança gravada para um ref que não existe passa no gate e lê a gaveta errada.

    O dispositivo seria reconhecido, o `Terminal.default()` assumiria, e o balcão
    estaria operando a gaveta de outro — sem nenhum sintoma até o fechamento.
    """
    client.force_login(gerente)

    resposta = client.post(
        STATION_URL, {"terminal_ref": "pdv-fantasma"}, content_type="application/json"
    )

    assert resposta.status_code == 400
    assert resposta.json()["error"]["code"] == "terminal_unknown"
    assert not TrustedDevice.objects.filter(subject_type=SubjectType.STATION).exists()


def test_terminal_inativo_e_recusado(client, gerente, terminal):
    terminal.is_active = False
    terminal.save(update_fields=["is_active"])
    client.force_login(gerente)

    resposta = client.post(
        STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json"
    )

    assert resposta.status_code == 400


def test_a_tela_de_provisionamento_ve_o_estado_e_as_opcoes(client, gerente, terminal):
    Terminal.objects.create(ref="pdv-2", label="Balcão do fundo")
    client.force_login(gerente)

    antes = client.get(STATION_URL).json()
    assert antes["station"] == ""
    assert [t["ref"] for t in antes["terminals"]] == ["pdv-2", "pdv-main"]

    client.post(STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json")

    assert client.get(STATION_URL).json()["station"] == terminal.ref


def test_revogar_mata_a_confianca_no_banco(client, gerente, terminal):
    """Tirar o cookie não basta: um token copiado antes continuaria valendo.

    É o caminho de quem está com a máquina na mão — desativar o quiosque que vai
    sair da loja. O dispositivo perdido continua revogável pelo Admin.
    """
    client.force_login(gerente)
    client.post(STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json")

    resposta = client.delete(f"{STATION_URL}?terminal_ref={terminal.ref}")

    assert resposta.status_code == 200
    assert not TrustedDevice.objects.filter(
        subject_type=SubjectType.STATION, is_active=True
    ).exists()


def test_provisionar_duas_vezes_nao_polui_a_auditoria(client, gerente, terminal):
    """Abrir a tela de novo no mesmo dispositivo não cria um segundo dispositivo."""
    client.force_login(gerente)
    client.post(STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json")
    client.post(STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json")

    assert TrustedDevice.objects.filter(subject_type=SubjectType.STATION).count() == 1


def test_gerente_repara_dois_vinculos_com_escolha_explicita(client, gerente, terminal):
    """O rollout não deixa balcão+totem preso no estado ambíguo legado."""
    outro = Terminal.objects.create(ref="totem", label="Totem")
    trust_station(client, terminal.ref)
    trust_station(client, outro.ref)
    client.force_login(gerente)

    resposta = client.post(
        STATION_URL, {"terminal_ref": outro.ref}, content_type="application/json"
    )

    assert resposta.status_code == 200
    assert client.get(STATION_URL).json()["station"] == outro.ref
    assert not TrustedDevice.objects.get(subject_id=terminal.ref).is_valid
    assert TrustedDevice.objects.get(subject_id=outro.ref).is_valid


def test_reparo_preserva_outro_dispositivo(client, gerente, terminal):
    """Trocar ESTE navegador não revoga outro balcão que usa o mesmo terminal."""
    outro_terminal = Terminal.objects.create(ref="totem", label="Totem")
    outro_navegador = type(client)()
    trust_station(outro_navegador, terminal.ref)
    dispositivo_alheio = TrustedDevice.objects.get(subject_id=terminal.ref)
    trust_station(client, terminal.ref)
    dispositivo_local = TrustedDevice.objects.filter(subject_id=terminal.ref).exclude(
        pk=dispositivo_alheio.pk
    ).get()
    trust_station(client, outro_terminal.ref)
    client.force_login(gerente)

    resposta = client.post(
        STATION_URL,
        {"terminal_ref": outro_terminal.ref},
        content_type="application/json",
    )

    assert resposta.status_code == 200
    dispositivo_alheio.refresh_from_db()
    dispositivo_local.refresh_from_db()
    assert dispositivo_alheio.is_valid
    assert not dispositivo_local.is_valid


def test_reparo_substitui_cookie_expirado(client, gerente, terminal):
    outro = Terminal.objects.create(ref="antigo", label="Antigo")
    trust_station(client, outro.ref)
    expirado = TrustedDevice.objects.get(subject_id=outro.ref)
    expirado.expires_at = timezone.now() - timedelta(seconds=1)
    expirado.save(update_fields=["expires_at"])
    client.force_login(gerente)

    resposta = client.post(
        STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json"
    )

    assert resposta.status_code == 200
    assert resposta.cookies[station_trust.station_cookie_name(outro.ref)]["max-age"] == 0
    assert client.get(STATION_URL).json()["station"] == terminal.ref


def test_provisionamento_anonimo_e_recusado(client, terminal):
    resposta = client.post(
        STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json"
    )

    assert resposta.status_code in {401, 403}
    assert not TrustedDevice.objects.filter(subject_type=SubjectType.STATION).exists()


def test_provisionamento_por_sessao_exige_csrf(gerente, terminal):
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(gerente)

    resposta = csrf_client.post(
        STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json"
    )

    assert resposta.status_code == 403
    assert not TrustedDevice.objects.filter(subject_type=SubjectType.STATION).exists()


def test_um_dispositivo_ja_provisionado_nao_precisa_de_gerente_para_pedir_PIN(client, terminal):
    """O contrapeso do gate: `manage_operators` guarda o PROVISIONAMENTO, não o uso.

    Se guardasse o uso, a antessala exigiria gerente e a loja não abriria — que é
    o defeito que este arranjo inteiro existe para evitar.
    """
    trust_station(client, terminal.ref)

    sessao = client.get(reverse("api-backstage-operator-session"))

    assert sessao.status_code == 200
    assert sessao.json()["station"] == terminal.ref
    assert station_trust.PROVISION_PERM == "cashman.manage_operators"


# ── Vários dispositivos no mesmo balcão, com visibilidade (D-007, WP-2) ──────


def test_segundo_dispositivo_no_mesmo_balcao_pede_confirmacao(client, gerente, terminal):
    """Não recusa (D-007): avisa, e só passa com a segunda palavra."""
    trust_station(Client(), terminal.ref)
    client.force_login(gerente)

    sem = client.post(STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json")

    assert sem.status_code == 409
    corpo = sem.json()
    assert corpo["error"]["code"] == "station_terminal_shared"
    assert corpo["field"] == "confirm"
    assert corpo["errors"] == {"confirm": [corpo["detail"]]}
    assert "1 outro dispositivo" in corpo["detail"]
    assert corpo["error"]["context"] == {"terminal_ref": terminal.ref, "other_devices": 1}
    assert len(station_trust.active_station_devices(terminal.ref)) == 1

    com = client.post(
        STATION_URL, {"terminal_ref": terminal.ref, "confirm": True}, content_type="application/json"
    )

    assert com.status_code == 200
    assert len(station_trust.active_station_devices(terminal.ref)) == 2


def test_reprovisionar_o_proprio_dispositivo_nao_pede_confirmacao(client, gerente, terminal):
    client.force_login(gerente)
    client.post(STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json")

    de_novo = client.post(STATION_URL, {"terminal_ref": terminal.ref}, content_type="application/json")

    assert de_novo.status_code == 200


def test_a_lista_de_terminais_traz_a_ocupacao(client, gerente, terminal):
    from shopman.backstage.services import pos as pos_service

    Terminal.objects.create(ref="pdv-2", label="Balcão do fundo")
    trust_station(Client(), terminal.ref)
    trust_station(Client(), terminal.ref)
    pos_service.open_cash_shift(operator=gerente, terminal_ref=terminal.ref)
    client.force_login(gerente)

    terminais = {t["ref"]: t for t in client.get(STATION_URL).json()["terminals"]}

    assert terminais["pdv-main"]["active_devices"] == 2
    assert terminais["pdv-main"]["has_open_shift"] is True
    assert terminais["pdv-2"]["active_devices"] == 0
    assert terminais["pdv-2"]["has_open_shift"] is False


def test_revogar_um_dispositivo_do_balcao_derruba_so_ele(terminal):
    trust_station(Client(), terminal.ref)
    trust_station(Client(), terminal.ref)
    um, outro = station_trust.active_station_devices(terminal.ref)

    um.revoke()

    assert [d.pk for d in station_trust.active_station_devices(terminal.ref)] == [outro.pk]


def test_admin_do_terminal_lista_os_dispositivos_e_leva_a_revogacao(terminal):
    from django.contrib import admin as django_admin

    admin_do_terminal = django_admin.site._registry[Terminal]
    assert "2 dispositivos" not in str(admin_do_terminal.station_devices_display(terminal))

    trust_station(Client(), terminal.ref)
    trust_station(Client(), terminal.ref)
    html = str(admin_do_terminal.station_devices_display(terminal))

    assert "2 dispositivos" in html
    assert html.count("<li>") == 2
    assert "subject_type__exact=station" in html and f"subject_id={terminal.ref}" in html


def test_o_caixa_do_balcao_diz_quantos_dispositivos_ha(terminal):
    """A projeção do caixa informa N; é informação, não o `terminal_occupied` de volta."""
    from shopman.backstage.projections.pos import POSCashRuntimeProjection, _cash_runtime_projection
    from shopman.backstage.services.pos_terminal import runtime_profile

    trust_station(Client(), terminal.ref)
    trust_station(Client(), terminal.ref)

    runtime = runtime_profile(terminal)
    projecao = _cash_runtime_projection(None, runtime, None, terminal=terminal)

    assert projecao.station_devices == 2
    assert projecao.status == "closed"
    assert "terminal_occupied" not in POSCashRuntimeProjection.__dataclass_fields__
