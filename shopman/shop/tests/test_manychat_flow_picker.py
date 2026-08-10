"""O flow do WhatsApp escolhido por NOME, e o que acontece quando a API não responde.

O `ns` é opaco (`content20240614222050_512341`) e a falha dele é silenciosa: ns errado não
estoura, só faz a onda falhar destinatário por destinatário com erro do provedor. Por isso
o Admin oferece a lista por nome — e por isso os casos de borda importam mais que o caminho
felizardo:

· API fora ou sem token → o campo volta a ser TEXTO LIVRE, não trava o formulário;
· flow apagado no ManyChat → continua visível na lista, marcado, porque sumir com ele
  esconderia justamente a causa da campanha que falha calada.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache

from shopman.shop.admin.shop import NotificationTemplateForm
from shopman.shop.models import NotificationTemplate
from shopman.shop.services import manychat_flows

pytestmark = pytest.mark.django_db

FLOWS = (
    ("content20240614222050_512341", "Teste Webhook API Manychat"),
    ("content20210201131015_377918", "Arrays"),
)


@pytest.fixture(autouse=True)
def clean_cache():
    cache.delete("shopman.manychat.flows.v1")
    yield
    cache.delete("shopman.manychat.flows.v1")


@pytest.fixture
def with_flows(monkeypatch):
    monkeypatch.setattr(manychat_flows, "list_flows", lambda **kw: FLOWS)


@pytest.fixture
def without_flows(monkeypatch):
    """A API não respondeu, ou não há token — os dois casos são o mesmo para a tela."""
    monkeypatch.setattr(manychat_flows, "list_flows", lambda **kw: ())


def _template(ns: str = "") -> NotificationTemplate:
    return NotificationTemplate.objects.create(
        event="announcement_published", subject="", body="oi", whatsapp_flow_ns=ns
    )


def test_the_field_offers_flows_by_name(with_flows):
    form = NotificationTemplateForm(instance=_template())
    labels = [label for _value, label in form.fields["whatsapp_flow_ns"].choices]

    assert any("Teste Webhook API Manychat" in label for label in labels)
    assert any("Arrays" in label for label in labels)


def test_the_empty_option_says_what_empty_means(with_flows):
    form = NotificationTemplateForm(instance=_template())
    empty = [label for value, label in form.fields["whatsapp_flow_ns"].choices if value == ""]

    assert empty and "24h" in empty[0], "o operador precisa saber o custo de deixar vazio"


def test_without_the_api_the_field_stays_free_text(without_flows):
    """Não travar o operador é mais importante que forçar a lista."""
    form = NotificationTemplateForm(instance=_template())
    field = form.fields["whatsapp_flow_ns"]

    assert not getattr(field, "choices", None), "sem lista, não vira ChoiceField"
    assert "manychat_flows" in field.help_text, "a ajuda tem de dizer como descobrir o ns"


def test_a_deleted_flow_stays_visible_and_marked(with_flows):
    """Flow apagado no ManyChat é a causa da campanha que falha calada. Não esconder."""
    form = NotificationTemplateForm(instance=_template("content20200101000000_000000"))
    choices = dict(form.fields["whatsapp_flow_ns"].choices)

    assert "content20200101000000_000000" in choices
    assert "apagado" in choices["content20200101000000_000000"]


def test_a_valid_flow_is_not_marked_as_deleted(with_flows):
    form = NotificationTemplateForm(instance=_template(FLOWS[0][0]))
    choices = dict(form.fields["whatsapp_flow_ns"].choices)

    assert "apagado" not in choices[FLOWS[0][0]]


def test_choosing_a_flow_saves_the_ns(with_flows):
    template = _template()
    form = NotificationTemplateForm(
        data={
            "event": template.event,
            "subject": "Novidade na padaria",
            "body": "oi",
            "whatsapp_flow_ns": FLOWS[0][0],
            "is_active": True,
        },
        instance=template,
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.whatsapp_flow_ns == FLOWS[0][0]


def test_empty_stays_allowed(with_flows):
    """Sem flow é configuração legítima: texto livre dentro da janela de 24h."""
    template = _template(FLOWS[0][0])
    form = NotificationTemplateForm(
        data={"event": template.event, "subject": "Novidade na padaria", "body": "oi",
              "whatsapp_flow_ns": "", "is_active": True},
        instance=template,
    )
    assert form.is_valid(), form.errors
    assert form.save().whatsapp_flow_ns == ""


# ── O serviço por baixo ──────────────────────────────────────────────


def test_no_token_means_empty_not_an_exception(monkeypatch):
    monkeypatch.setattr("django.conf.settings.MANYCHAT_API_TOKEN", "", raising=False)
    assert manychat_flows.list_flows(force=True) == ()


def test_the_list_is_cached(monkeypatch):
    calls = {"n": 0}

    def _fake():
        calls["n"] += 1
        return FLOWS

    monkeypatch.setattr(manychat_flows, "_fetch", _fake)
    manychat_flows.list_flows(force=True)
    manychat_flows.list_flows()
    manychat_flows.list_flows()

    assert calls["n"] == 1, "o Admin renderiza muito; uma chamada de rede por render não"


def test_flow_name_resolves_and_admits_ignorance(monkeypatch):
    monkeypatch.setattr(manychat_flows, "_fetch", lambda: FLOWS)
    manychat_flows.list_flows(force=True)

    assert manychat_flows.flow_name(FLOWS[0][0]) == "Teste Webhook API Manychat"
    assert manychat_flows.flow_name("content20200101000000_000000") == ""
    assert manychat_flows.flow_name("") == ""
