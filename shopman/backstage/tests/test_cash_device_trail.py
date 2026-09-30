"""O dispositivo no rastro do DINHEIRO (WP-6).

A pergunta do dono é sobre fraude na gaveta. O WP-1 pôs o dispositivo na trilha de
ACESSO; aqui ele entra onde o dinheiro é lançado (``cashman.Entry.payload``) e nos
eventos da comanda (``SessionEvent.payload``), com o MESMO identificador: o
``TrustedDevice.pk`` da estação. Só assim "quem entrou neste tablet" cruza com "o
que ele lançou nesta gaveta".

Todos os testes passam pelo caminho HTTP do PDV. Chamar o serviço direto não prova
nada: o defeito é justamente um caminho que "deveria" carimbar e não carimba.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse
from shopman.cashman.models import Entry, Shift, Terminal
from shopman.doorman.models import PinCredential, TrustedDevice
from shopman.orderman.models import SessionEvent

from shopman.backstage.models import SignInEvent
from shopman.backstage.tests.support import trust_station

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("_loja")]

PIN = "1234"
KEY = "station_device_id"


@pytest.fixture
def _loja():
    from shopman.offerman.models import Product

    from shopman.shop.models import Channel, Shop

    Shop.objects.create(name="Nelson")
    Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
    Product.objects.create(sku="PAO", name="Pão", base_price_q=1200, is_published=True, is_sellable=True)


def _grant(user, *codenames):
    ct = ContentType.objects.get_for_model(Shift)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))
    return get_user_model().objects.get(pk=user.pk)


@pytest.fixture
def terminal():
    return Terminal.objects.create(ref="balcao", label="Balcão")


@pytest.fixture
def joyce():
    user = _grant(get_user_model().objects.create_user("joyce", password="x", is_staff=True), "operate_pos")
    PinCredential.set_for(user, PIN)
    return user


def _tablet(terminal, operator) -> tuple[Client, str]:
    """Um tablet do balcão: estação confiável + pessoa identificada por PIN."""
    client = Client()
    antes = set(TrustedDevice.objects.values_list("pk", flat=True))
    trust_station(client, terminal.ref)
    (device_pk,) = set(TrustedDevice.objects.values_list("pk", flat=True)) - antes
    resposta = client.post(
        reverse("api-backstage-operator-unlock"),
        {"operator_id": operator.pk, "pin": PIN, "perm": "cashman.operate_pos"},
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content
    return client, str(device_pk)


def _abre_caixa(client, terminal):
    resposta = client.post(
        reverse("api-backstage-pos-cash-open"),
        {"opening_amount": "100,00", "terminal_ref": terminal.ref, "client_request_id": "trail-open"},
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content
    return resposta.json()["shift_id"]


def _suprimento(client, request_id: str):
    resposta = client.post(
        reverse("api-backstage-pos-cash-movement"),
        {"kind": "suprimento", "amount": "10,00", "reason": "troco", "client_request_id": request_id},
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content


def test_o_lancamento_de_caixa_pelo_pdv_carrega_o_dispositivo(terminal, joyce):
    tablet, device = _tablet(terminal, joyce)

    shift_id = _abre_caixa(tablet, terminal)
    _suprimento(tablet, "trail-in-1")

    fundo = Entry.objects.get(shift_id=shift_id, kind=Entry.Kind.FLOAT_IN)
    entrada = Entry.objects.get(shift_id=shift_id, kind=Entry.Kind.CASH_IN)
    assert fundo.payload[KEY] == device
    assert entrada.payload[KEY] == device


def test_dois_tablets_no_mesmo_balcao_lancam_com_ids_diferentes(terminal, joyce):
    """Mesma pessoa, mesmo turno, mesma gaveta: o que separa os dois é o dispositivo."""
    frente, device_frente = _tablet(terminal, joyce)
    fundo, device_fundo = _tablet(terminal, joyce)
    assert device_frente != device_fundo

    _abre_caixa(frente, terminal)
    _suprimento(frente, "trail-frente")
    _suprimento(fundo, "trail-fundo")

    entradas = {e.payload[KEY] for e in Entry.objects.filter(kind=Entry.Kind.CASH_IN)}
    assert entradas == {device_frente, device_fundo}


def test_o_mesmo_id_cruza_a_trilha_de_acesso_com_o_livro(terminal, joyce):
    """A pergunta que motivou tudo: quem entrou NESTE tablet lançou O QUÊ nesta gaveta."""
    tablet, device = _tablet(terminal, joyce)
    _abre_caixa(tablet, terminal)
    _suprimento(tablet, "trail-cruza")

    acesso = SignInEvent.objects.get(data__station_device_id=device)
    lancamentos = Entry.objects.filter(payload__station_device_id=device)
    assert acesso.user == joyce
    assert set(lancamentos.values_list("kind", flat=True)) == {Entry.Kind.FLOAT_IN, Entry.Kind.CASH_IN}


def test_o_corpo_nao_escolhe_o_dispositivo(terminal, joyce):
    """Quem diz qual dispositivo agiu é a requisição, nunca o payload do chamador."""
    from shopman.cashman import services as cash

    tablet, device = _tablet(terminal, joyce)
    shift_id = _abre_caixa(tablet, terminal)

    entry = cash.record(
        Entry.Kind.NOTE, shift=Shift.objects.get(pk=shift_id), operator=joyce, payload={KEY: "forjado"},
    )

    # Fora de requisição não há dispositivo: a chave forjada some, não vira trilha.
    assert KEY not in entry.payload


def test_o_evento_da_comanda_pelo_pdv_carrega_o_dispositivo(terminal, joyce):
    tablet, device = _tablet(terminal, joyce)
    _abre_caixa(tablet, terminal)
    aberta = tablet.post(reverse("api-backstage-pos-tab-open", args=["12"]), content_type="application/json")
    assert aberta.status_code == 200, aberta.content
    tab = aberta.json()

    salva = tablet.post(
        reverse("api-backstage-pos-tab-save"),
        {
            "tab_session_key": tab["session_key"],
            "expected_revision": tab["revision"],
            "items": [{"line_id": "L-trail01", "sku": "PAO", "qty": 1, "unit_price_q": 1200}],
        },
        content_type="application/json",
    )

    assert salva.status_code == 200, salva.content
    evento = SessionEvent.objects.get(session_key=tab["session_key"], type="line_added")
    assert evento.payload[KEY] == device


def test_o_dispositivo_nao_vaza_para_as_telas_do_caixa(terminal, joyce):
    """O lançamento segue legível na antesala de quem opera, e o dispositivo não aparece."""
    tablet, device = _tablet(terminal, joyce)
    _abre_caixa(tablet, terminal)
    _suprimento(tablet, "trail-tela")
    assert Entry.objects.filter(payload__station_device_id=device).exists()

    antesala = tablet.get("/api/v1/backstage/pos/")

    assert antesala.status_code == 200, antesala.content
    assert antesala.json()["pos"]["cash_runtime"]["has_open_shift"] is True
    corpo = json.dumps(antesala.json())
    assert device not in corpo and KEY not in corpo

    auditora = _grant(get_user_model().objects.create_user("dona", password="x", is_staff=True), "operate_pos", "audit_shift")
    tablet.force_login(auditora)
    relatorio = tablet.get(reverse("api-backstage-pos-cash-report"))
    assert relatorio.status_code == 200, relatorio.content
    assert relatorio.json()["report"]["x_reading"]["movements"]
    corpo = json.dumps(relatorio.json())
    assert device not in corpo and KEY not in corpo
