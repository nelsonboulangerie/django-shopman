"""A variável do template aprovado precisa de alguém que a preencha.

Este arquivo existe por causa de um defeito silencioso. Quando o evento tem flow
configurado, o envio vai por `sendFlow`: o texto vive **dentro do ManyChat**, e as
variáveis dele saem dos campos personalizados do assinante — **não** do `flow_token` que
mandávamos. Resultado: um template aprovado que diga "O {{product_name}} que você pediu
chegou" saía com o nome do produto em branco, nos dois caminhos que usam flow (alerta de
estoque e anúncio de campanha). Nada falhava; a mensagem só chegava incompleta.

O teste que guarda o desenho é `test_the_fields_go_before_the_flow`: gravar depois do
envio seria escrever no perfil do cliente para a mensagem seguinte, não para esta.
"""

from __future__ import annotations

import pytest

from shopman.shop.adapters import notification_manychat as mc

pytestmark = pytest.mark.django_db


@pytest.fixture
def calls(monkeypatch):
    """Registra cada chamada à API, na ordem, sem tocar a rede."""
    seen: list[tuple[str, dict]] = []

    def _fake(endpoint, payload, config):
        seen.append((endpoint, payload))
        return {"success": True}

    monkeypatch.setattr(mc, "_api_call", _fake)
    monkeypatch.setattr(mc, "_get_config", lambda: {"api_token": "tok", "flow_map": {}})
    monkeypatch.setattr(mc, "_resolve_subscriber", lambda *a, **k: "sub-1")
    return seen


@pytest.fixture
def with_flow(db):
    from shopman.shop.models import NotificationTemplate

    NotificationTemplate.objects.create(
        event="stock_arrived", subject="x", body="y",
        whatsapp_flow_ns="content20260101120000_1",
    )


def _endpoints(calls) -> list[str]:
    return [endpoint for endpoint, _payload in calls]


def _field_payloads(calls) -> dict[str, str]:
    return {
        payload["field_name"]: payload["field_value"]
        for endpoint, payload in calls
        if endpoint.endswith("setCustomFieldByName")
    }


def test_the_fields_go_before_the_flow(calls, with_flow, monkeypatch):
    """⚠️ Ordem importa: gravar depois do envio preencheria a mensagem SEGUINTE."""
    mc.send("+5543984049009", "stock_arrived", {"product_name": "Croissant"})

    endpoints = _endpoints(calls)
    assert endpoints[-1].endswith("sendFlow")
    assert any(e.endswith("setCustomFieldByName") for e in endpoints[:-1])


def test_the_product_name_reaches_the_template(calls, with_flow):
    """O caso concreto: sem isto, "O ___ que você pediu chegou"."""
    mc.send(
        "+5543984049009",
        "stock_arrived",
        {"product_name": "Croissant", "cta": "Garanta o seu:", "action_url": "/p/cro"},
    )

    fields = _field_payloads(calls)
    assert fields["product_name"] == "Croissant"
    assert fields["action_url"] == "/p/cro"


def test_internal_state_never_becomes_a_customer_field(calls, with_flow):
    """⚠️ Contexto inteiro no perfil do cliente vazaria estado interno para o marketing."""
    mc.send(
        "+5543984049009",
        "stock_arrived",
        {"product_name": "Croissant", "session_key": "abc123", "sku": "CRO-001"},
    )

    fields = _field_payloads(calls)
    assert "session_key" not in fields
    assert "sku" not in fields
    assert "product_name" in fields


def test_empty_values_are_not_written(calls, with_flow):
    """`deadline_note` vazio é o caso normal do "me avise": não sobrescreve com nada."""
    mc.send(
        "+5543984049009",
        "stock_arrived",
        {"product_name": "Croissant", "deadline_note": "", "reserve_note": "   "},
    )

    fields = _field_payloads(calls)
    assert "deadline_note" not in fields
    assert "reserve_note" not in fields


def test_a_field_that_does_not_exist_does_not_block_the_alert(with_flow, monkeypatch):
    """Alerta de fornada é tempo-sensível: mensagem com pedaço faltando ainda avisa."""
    seen: list[str] = []

    def _fake(endpoint, payload, config):
        seen.append(endpoint)
        if endpoint.endswith("setCustomFieldByName"):
            return {"success": False, "error": "field not found"}
        return {"success": True}

    monkeypatch.setattr(mc, "_api_call", _fake)
    monkeypatch.setattr(mc, "_get_config", lambda: {"api_token": "tok", "flow_map": {}})
    monkeypatch.setattr(mc, "_resolve_subscriber", lambda *a, **k: "sub-1")

    assert mc.send("+5543984049009", "stock_arrived", {"product_name": "Croissant"}) is True
    assert any(e.endswith("sendFlow") for e in seen)


def test_without_a_flow_nothing_is_pushed(calls, db):
    """Sem template aprovado o texto é nosso (`sendContent`): campo não tem função."""
    mc.send("+5543984049009", "stock_arrived", {"product_name": "Croissant"})

    endpoints = _endpoints(calls)
    assert endpoints == ["/sending/sendContent"]


# ── A quantidade que a mensagem promete ──────────────────────────────


def test_the_quantity_is_the_real_one(calls, with_flow):
    """⚠️ FOMO com número só vale se o número for verdade.

    A quantidade sai da MESMA checagem de disponibilidade que libera o alerta, então o
    "ainda tenho X unidades" é o que a loja pode honrar naquele instante.
    """
    mc.send("+5543984049009", "stock_arrived", {"product_name": "Baguete", "available_qty": "12"})

    assert _field_payloads(calls)["available_qty"] == "12"


def test_an_unknown_quantity_says_nothing(calls, with_flow):
    """Canal que não sabe contar não inventa número: o campo não é gravado."""
    mc.send("+5543984049009", "stock_arrived", {"product_name": "Baguete", "available_qty": ""})

    assert "available_qty" not in _field_payloads(calls)


# ── Um template, dois caminhos ───────────────────────────────────────


#: O que a mensagem de "produto disponível" precisa saber, venha de onde vier. São os
#: campos que o gestor cria no ManyChat — se um caminho parar de mandar um deles, o
#: template renderiza vazio para metade das pessoas.
SHARED_FIELDS = {"customer_name", "product_name", "product_ref", "available_qty"}


def test_both_paths_speak_the_same_vocabulary():
    """⚠️ O gatilho é UM (fornada excelente) e o público é misto: quem favoritou e quem
    pediu para avisar recebem o MESMO anúncio.

    Por isso o template é genérico — e um template genérico só funciona se os dois
    caminhos que o alimentam falarem igual. Já falaram diferente: campanha mandava
    `nome`/`stock`/`sku`, alerta mandava `customer_name`/`available_qty`/`product_ref`.
    """
    from shopman.shop.services.campaign import available_variables

    campaign_vocabulary = set(available_variables())
    assert SHARED_FIELDS <= campaign_vocabulary, SHARED_FIELDS - campaign_vocabulary


def test_the_campaign_path_sends_the_shared_fields(db, monkeypatch):
    """O handler de campanha manda os campos com os nomes compartilhados."""
    from shopman.shop.handlers import campaign as handler

    seen: list[dict] = []
    monkeypatch.setattr(handler, "_whatsapp_backend", lambda: "manychat")
    monkeypatch.setattr(
        "shopman.shop.notifications.notify",
        lambda **kw: seen.append(kw.get("context") or {}) or type("R", (), {"success": True})(),
    )

    recipient = type("R", (), {"phone": "+5543984049009", "first_name": "Pablo"})()
    content = {
        "body": "Saiu do forno",
        "variables": {
            "product_name": "Baguete", "product_ref": "BAGUETE", "available_qty": "12",
        },
    }
    announcement = type(
        "A", (), {"pk": 1, "body": "Saiu do forno", "content": content, "platform_results": {}}
    )()

    handler._send_to([recipient], announcement=announcement)

    assert seen, "nada foi enviado"
    assert SHARED_FIELDS <= set(seen[0]), SHARED_FIELDS - set(seen[0])
    assert seen[0]["customer_name"] == "Pablo"
    assert seen[0]["available_qty"] == "12"
