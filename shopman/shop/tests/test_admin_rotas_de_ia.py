"""A IA de cada função escolhida por lista na página Integrações, e a decisão em sombra (#2843, #2842).

Pedido do dono (19/11/2026): "isso deveria ser exatamente configuravel via admin ok!".

- por função, a conexão ativa e o modelo numa lista; nada de JSON;
- ao lado, se a função está pronta, ou o motivo de ``ai.explain`` e o botão que resolve;
- rota parada (conexão inativa, sem chave, não liberada) vira aviso no topo, com o botão;
- a caixa da decisão em sombra liga e desliga, e o histórico diz quem fez.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from shopman.shop import ai
from shopman.shop.admin import ai_routes
from shopman.shop.admin.shop import _INTEGRATIONS_FIELDSETS, _section_form
from shopman.shop.models import AIConnection, AIProtocol, Shop

pytestmark = pytest.mark.django_db

MARKETING_FIELDS = (
    "integrations_payment_pix",
    "integrations_payment_card",
    "integrations_notification_default",
    "integrations_fiscal",
    "defaults_marketing_whatsapp_minimum_audience",
    "defaults_marketing_ceremony_audience_percent",
    "defaults_marketing_ceremony_spend_limit_q",
    "defaults_marketing_direct_message_cost_q",
    "defaults_marketing_ceremony_recipient_floor",
    "defaults_marketing_ceremony_dual_control_multiple",
)


def _connection(ref, *, key="sk-test", active=True, base_url="", model="claude-sonnet-5-5", customer=True):
    connection = AIConnection.objects.create(
        ref=ref, name=ref.title(), protocol=AIProtocol.ANTHROPIC, base_url=base_url, model=model,
        customer_text_approved=customer, is_active=active,
    )
    connection.set_api_key(key)
    connection.save()
    return connection


@pytest.fixture
def shop():
    AIConnection.objects.all().delete()  # a 0116 semeia conexões; cada teste diz as suas
    return Shop.objects.create(name="Nelson Boulangerie")


@pytest.fixture
def admin_client(admin_user):
    client = Client()
    client.force_login(admin_user)
    return client


def _url(shop):
    return reverse("admin:shop_shopintegrations_change", args=[shop.pk])


def _form(shop, data=None):
    Form = _section_form(_INTEGRATIONS_FIELDSETS)
    return Form(data=data, instance=shop) if data is not None else Form(instance=shop)


def _data(**routes):
    data = dict.fromkeys(MARKETING_FIELDS, "")
    data["ai_limits"] = "{}"
    data["incident_remedies_mode"] = "on"
    for key in ai_routes.ROUTE_KEYS:
        data[ai_routes.connection_field(key)] = ""
        data[ai_routes.model_field(key)] = ""
    data.update(routes)
    return data


def test_each_function_is_two_lists_and_the_json_is_gone(shop):
    _connection("anthropic")
    _connection("velha", active=False)
    fields = _form(shop).fields

    assert "ai_routes" not in fields
    for key in ai_routes.ROUTE_KEYS:
        assert isinstance(fields[ai_routes.connection_field(key)].widget.choices, list)
    refs = [ref for ref, _label in fields[ai_routes.connection_field("concierge")].choices]
    assert refs == ["", "anthropic"], "só conexão ativa do formato entra na lista"
    models = [model for model, _label in fields[ai_routes.model_field("concierge")].choices]
    assert models[0] == "" and "claude-sonnet-5-5" in models and "deepseek-flash" in models
    assert fields[ai_routes.connection_field("concierge")].label == ai.PURPOSES["concierge"]


def test_saving_the_lists_writes_the_routes_and_keeps_unknown_keys(admin_client, shop):
    _connection("anthropic")
    _connection("deepseek", base_url="https://api.deepseek.com/anthropic", model="deepseek-flash")
    shop.ai_routes = {"concierge": {"connection": "anthropic", "max_tokens": 900}, "experimento": {"x": 1}}
    shop.save()

    response = admin_client.post(_url(shop), _data(**{
        ai_routes.connection_field("default"): "anthropic",
        ai_routes.connection_field("concierge"): "anthropic",
        ai_routes.model_field("concierge"): "claude-opus-5-5",
        ai_routes.connection_field("copy"): "deepseek",
    }))

    assert response.status_code == 302, response.context_data["adminform"].form.errors
    shop.refresh_from_db()
    assert shop.ai_routes == {
        "default": {"connection": "anthropic"},
        "concierge": {"connection": "anthropic", "max_tokens": 900, "model": "claude-opus-5-5"},
        "copy": {"connection": "deepseek"},
        "experimento": {"x": 1},
    }
    assert ai.resolve("concierge").model == "claude-opus-5-5"
    assert ai.resolve("copy").ref == "deepseek"


def test_a_model_from_another_vendor_or_without_a_connection_is_refused(shop):
    _connection("deepseek", base_url="https://api.deepseek.com/anthropic", model="deepseek-flash")
    form = _form(shop, _data(**{
        ai_routes.connection_field("copy"): "deepseek",
        ai_routes.model_field("copy"): "claude-opus-5-5",
        ai_routes.model_field("recipe"): "deepseek-flash",
    }))

    assert not form.is_valid()
    assert "não roda na conexão" in form.errors[ai_routes.model_field("copy")][0]
    assert "Escolha a conexão desta função antes do modelo" in form.errors[ai_routes.model_field("recipe")][0]


def test_next_to_each_function_ready_or_the_reason_with_the_button(admin_client, shop):
    ready = _connection("anthropic")
    _connection("semchave", key="")
    shop.ai_routes = {"default": {"connection": "anthropic"}, "triage": {"connection": "semchave"}}
    shop.save()

    assert ai_routes.readiness("concierge").ready
    stopped = ai_routes.readiness("triage")
    assert not stopped.ready and stopped.text == ai.explain("triage")
    assert stopped.fix_url == reverse(
        "admin:shop_aiconnection_change", args=[AIConnection.objects.get(ref="semchave").pk]
    )
    body = admin_client.get(_url(shop)).content.decode()
    assert f"Pronta: {ready.name} · claude-sonnet-5-5" in body, "o nome da conexão, não a ref"
    assert "Parada: a conexão de IA &#x27;semchave&#x27; está sem chave." in body


def test_a_route_to_an_inactive_connection_is_a_warning_on_top_with_the_button(admin_client, shop):
    _connection("anthropic")
    off = _connection("desligada", active=False)
    shop.ai_routes = {"default": {"connection": "anthropic"}, "concierge": {"connection": "desligada"},
                      "triage": {"connection": "desligada"}}
    shop.save()

    warnings = ai_routes.warnings()
    assert len(warnings) == 1, "um aviso por motivo, com as funções que ele para"
    assert warnings[0]["functions"] == "Concierge, Triagem das mensagens de clientes"
    assert "desligada" in warnings[0]["reason"]
    body = admin_client.get(_url(shop)).content.decode()
    assert "A IA está parada em Concierge, Triagem das mensagens de clientes" in body
    assert "&#x27;concierge&#x27;" not in body, "a chave interna da função não aparece"
    assert reverse("admin:shop_aiconnection_change", args=[off.pk]) in body
    # A rota gravada continua visível na lista, marcada, para não sumir em silêncio.
    choices = dict(_form(shop).fields[ai_routes.connection_field("concierge")].choices)
    assert choices["desligada"] == "desligada (está inativa)"


def test_a_function_never_turned_on_is_not_a_warning(shop):
    assert ai_routes.warnings() == []


def test_the_shadow_box_turns_on_and_off_and_the_history_says_who(admin_client, admin_user, shop):
    assert "conversational_shadow_enabled" in _form(shop).fields

    on = admin_client.post(_url(shop), _data(conversational_shadow_enabled="on"))
    assert on.status_code == 302
    shop.refresh_from_db()
    assert shop.conversational_shadow_enabled is True
    off = admin_client.post(_url(shop), _data())
    assert off.status_code == 302
    shop.refresh_from_db()
    assert shop.conversational_shadow_enabled is False
    admin_client.post(_url(shop), _data())  # salvar sem mudar não entra no histórico

    history = ai_routes.shadow_history(shop)
    assert [what for _when, _who, what in history] == [ai_routes.SHADOW_OFF, ai_routes.SHADOW_ON]
    assert {who for _when, who, _what in history} == {admin_user.get_username()}
    assert ai_routes.SHADOW_ON in admin_client.get(_url(shop)).content.decode()


def test_the_manager_reads_the_page_without_raw_names(client, shop):
    call_command("setup_groups")
    user = User.objects.create_user("gerente-ia", password="pw", is_staff=True)
    user.groups.add(Group.objects.get(name="Gerente"))
    client.force_login(user)

    body = client.get(_url(shop)).content.decode()
    assert "Ai route" not in body
    assert ai.PURPOSES["concierge"] in body


@pytest.mark.parametrize(
    ("setup", "cause"),
    [
        ("apagada", "não existe mais"),
        ("inativa", "está inativa"),
        ("jev", "é do formato Jev, não Anthropic"),
    ],
)
def test_the_reason_says_the_one_cause_that_holds_for_that_connection(admin_client, shop, setup, cause):
    """Defeito "o leitor escolhe entre leituras": a frase de ai.explain junta três causas."""
    _connection("anthropic")
    if setup == "inativa":
        _connection("alvo", active=False)
    elif setup == "jev":
        jev = _connection("alvo")
        jev.protocol = AIProtocol.JEV
        jev.save()
    shop.ai_routes = {"concierge": {"connection": "alvo"}}
    shop.save()

    expected = f"a rota aponta para a conexão 'alvo', que {cause}"
    assert ai_routes.readiness("concierge").text == expected
    assert ai_routes.warnings()[0]["reason"] == expected
    assert "ou é de outro formato" not in admin_client.get(_url(shop)).content.decode()
    label = dict(_form(shop).fields[ai_routes.connection_field("concierge")].choices)["alvo"]
    assert label == f"alvo ({cause})"


def test_the_reason_has_no_written_path_and_names_the_format(shop):
    """O botão leva à tela; o texto não descreve o caminho ("Admin → …") nem mostra a chave do formato."""
    _connection("anthropic")
    _connection("outra")
    text = ai_routes.readiness("decision").text
    assert text == "nenhuma conexão de IA ativa no formato Jev"
    ambiguous = ai_routes.readiness("copy")
    assert ambiguous.text.endswith("; escolha qual na lista desta função")
    assert ambiguous.fix_url == f"#id_{ai_routes.connection_field('copy')}"
    assert "→" not in text + ambiguous.text
