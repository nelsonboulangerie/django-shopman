"""Isolação POR CONSTRUÇÃO dos flows do ManyChat e os três modos do WhatsApp de Marketing.

O flow lê os CAMPOS PERSISTENTES do contato, depois, assíncrono. Duas mensagens com flow
para a mesma pessoa em sequência próxima (campanha da Baguete + aviso do Croissant)
podiam intercalar as escritas: a pessoa recebia nome, preço e link trocados.

A decisão (ADR-009, 17/09) não depende de prova do fornecedor: o adapter reserva o
assinante no cache compartilhado ANTES de escrever qualquer campo, por uma janela de
assentamento. Quem não reserva não escreve nada e volta depois — resultado retentável
(``subscriber_busy``), nunca falha final nem ``unknown``. A abertura é por modo:
``blocked`` (padrão) → ``canary`` (só refs listados) → ``open``.
"""

from __future__ import annotations

import time
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from shopman.shop import notifications
from shopman.shop.adapters import notification_manychat as mc
from shopman.shop.checks import check_marketing_whatsapp_isolation
from shopman.shop.models import DeliveryAttempt, DeliveryTarget, NotificationTemplate
from shopman.shop.services import manychat_marketing_safety as safety
from shopman.shop.services.marketing_contracts import (
    MarketingContractError,
    ProviderCallFailure,
    ProviderOutcome,
    ProviderOutcomeKind,
)

pytestmark = pytest.mark.django_db

SUBSCRIBER = 4242
LISTED = "CLI-CANARIO"


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def provider(monkeypatch):
    """ManyChat de mentira: registra cada chamada, na ordem, sem rede."""
    calls: list[tuple[str, dict]] = []

    def _fake(endpoint, payload, config):
        calls.append((endpoint, payload))
        return {"success": True}

    monkeypatch.setattr(mc, "_api_call", _fake)
    monkeypatch.setattr(mc, "_get_config", lambda: {"api_token": "synthetic", "flow_map": {}})
    monkeypatch.setattr(mc, "_resolve_subscriber", lambda *a, **k: SUBSCRIBER)
    return calls


@pytest.fixture
def flows(db):
    for event in ("announcement_published", "stock_arrived", "production_ready", "order_accepted"):
        NotificationTemplate.objects.create(
            event=event, subject="x", body="y", whatsapp_flow_ns=f"content_{event}",
        )


@pytest.fixture
def shared_cache(monkeypatch):
    """A suíte usa LocMem; aqui ele faz o papel do Redis (um processo só)."""
    monkeypatch.setattr(safety, "serialization_available", lambda: True)


@pytest.fixture
def open_mode(settings, shared_cache):
    settings.SHOPMAN_MARKETING_WHATSAPP_MODE = "open"


@pytest.fixture
def canary_mode(settings, shared_cache):
    settings.SHOPMAN_MARKETING_WHATSAPP_MODE = "canary"
    settings.SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS = (LISTED,)


def _flow_sends(calls) -> int:
    return sum(1 for endpoint, _payload in calls if endpoint.endswith("sendFlow"))


# ── 1. Serialização: uma mensagem com flow por assinante por vez ─────


@override_settings(DEBUG=False)
def test_second_flow_to_the_same_subscriber_inside_the_window_never_reaches_the_provider(
    provider, flows, open_mode
):
    first = mc.send("+5543999990001", "announcement_published", {"product_name": "Baguete"})
    calls_after_first = len(provider)
    second = mc.send("+5543999990001", "stock_arrived", {"product_name": "Croissant"})

    assert first is True
    assert _flow_sends(provider) == 1
    assert len(provider) == calls_after_first, "o segundo envio escreveu campo no contato"
    assert second == {
        "success": False,
        "error": "subscriber_busy",
        "retry_after_seconds": 120,
    }


@override_settings(DEBUG=False, SHOPMAN_MANYCHAT_FLOW_SETTLE_SECONDS=1)
def test_after_the_window_the_next_flow_goes_out(provider, flows, open_mode):
    assert mc.send("+5543999990001", "announcement_published", {"product_name": "Baguete"}) is True
    assert mc.send("+5543999990001", "stock_arrived", {"product_name": "Croissant"})["error"] == "subscriber_busy"

    time.sleep(1.2)

    assert mc.send("+5543999990001", "stock_arrived", {"product_name": "Croissant"}) is True
    assert _flow_sends(provider) == 2


@override_settings(DEBUG=False)
def test_reservation_is_taken_before_the_first_field_with_the_settle_timeout(
    provider, flows, open_mode, monkeypatch
):
    order: list[str] = []
    real_add = cache.add

    def spying_add(key, value, timeout=None, **kwargs):
        order.append(f"reserve:{key}:{timeout}")
        return real_add(key, value, timeout=timeout, **kwargs)

    monkeypatch.setattr(cache, "add", spying_add)
    real_api = mc._api_call
    monkeypatch.setattr(
        mc, "_api_call", lambda endpoint, payload, config: order.append(endpoint) or real_api(endpoint, payload, config)
    )

    mc.send("+5543999990001", "announcement_published", {"product_name": "Baguete"})

    assert order[0] == f"reserve:manychat:flow-busy:{SUBSCRIBER}:120"
    assert order[-1].endswith("sendFlow")


@override_settings(DEBUG=False)
def test_different_subscribers_do_not_wait_for_each_other(provider, flows, open_mode, monkeypatch):
    subscribers = iter((1001, 1002))
    monkeypatch.setattr(mc, "_resolve_subscriber", lambda *a, **k: next(subscribers))

    assert mc.send("+5543999990001", "announcement_published", {"product_name": "Baguete"}) is True
    assert mc.send("+5543999990002", "announcement_published", {"product_name": "Baguete"}) is True
    assert _flow_sends(provider) == 2


@override_settings(DEBUG=False)
def test_order_flows_are_serialized_too_but_send_content_is_not(provider, flows, monkeypatch):
    """A corrida é do FLOW, não do Marketing: pedido com flow também reserva."""
    assert mc.send("+5543999990001", "order_accepted", {"order_ref": "P-1"}) is True
    assert mc.send("+5543999990001", "order_accepted", {"order_ref": "P-2"})["error"] == "subscriber_busy"

    NotificationTemplate.objects.filter(event="order_accepted").update(whatsapp_flow_ns="")
    # sendContent não grava campo persistente: não há o que serializar.
    assert mc.send("+5543999990001", "order_accepted", {"order_ref": "P-3"}) is True


@override_settings(DEBUG=False)
def test_cache_outage_is_a_retryable_deferral_not_a_send(provider, flows, open_mode, monkeypatch):
    def broken_add(*args, **kwargs):
        raise ConnectionError("redis down")

    monkeypatch.setattr(cache, "add", broken_add)

    result = mc.send("+5543999990001", "announcement_published", {"product_name": "Baguete"})

    assert result["error"] == "flow_reservation_unavailable"
    assert provider == []


@override_settings(DEBUG=False)
def test_notify_turns_busy_into_a_retryable_result_never_unknown(provider, flows, open_mode, monkeypatch):
    mc.send("+5543999990001", "announcement_published", {"product_name": "Baguete"})
    monkeypatch.setattr(notifications, "_adapters", {"manychat": mc})

    result = notifications.notify(
        event="stock_arrived",
        recipient="+5543999990001",
        context={"product_name": "Croissant"},
        backend="manychat",
    )

    assert result.success is False
    assert result.error == "subscriber_busy"
    assert result.outcome_unknown is False
    assert result.retry_after_seconds == 120
    assert safety.is_flow_deferral(result.error)


# ── 1b. Campos obsoletos: o conjunto completo de cada evento ─────────


def _last_fields(calls) -> dict[str, str]:
    fields: dict[str, str] = {}
    for endpoint, payload in calls:
        if endpoint.endswith("setCustomFieldByName"):
            fields[payload["field_name"]] = payload["field_value"]
    return fields


def _fields_between_flows(calls) -> list[dict[str, str]]:
    """Os campos gravados antes de cada ``sendFlow``, um dict por mensagem."""
    batches: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for endpoint, payload in calls:
        if endpoint.endswith("setCustomFieldByName"):
            current[payload["field_name"]] = payload["field_value"]
        elif endpoint.endswith("sendFlow"):
            batches.append(current)
            current = {}
    return batches


@override_settings(DEBUG=False, SHOPMAN_MANYCHAT_FLOW_SETTLE_SECONDS=1)
def test_a_message_without_price_clears_the_price_of_the_previous_one(provider, flows, open_mode):
    """A com ``price``, B sem ``price``: B grava ``price=""``, nunca herda o de A."""
    assert mc.send(
        "+5543999990001",
        "announcement_published",
        {"body": "Baguete por R$ 12,00", "product_name": "Baguete", "price": "R$ 12,00"},
    ) is True
    time.sleep(1.2)
    assert mc.send(
        "+5543999990001",
        "announcement_published",
        {"body": "Croissant saiu do forno", "product_name": "Croissant"},
    ) is True

    first, second = _fields_between_flows(provider)
    assert first["price"] == "R$ 12,00"
    assert second["price"] == ""
    assert second["product_name"] == "Croissant"
    assert set(second) == set(safety.MARKETING_FLOW_FIELDS["announcement_published"])


@override_settings(DEBUG=False)
@pytest.mark.parametrize("event", sorted(safety.MARKETING_FLOW_EVENTS))
def test_every_marketing_event_writes_its_whole_declared_set_and_nothing_else(
    provider, flows, open_mode, event
):
    assert mc.send(
        "+5543999990001",
        event,
        {"product_name": "Baguete", "undeclared_secret": "x", "sku": "BE", "customer_ref": "CLI-1"},
    ) is True

    fields = _last_fields(provider)
    assert set(fields) == set(safety.MARKETING_FLOW_FIELDS[event])
    assert fields["product_name"] == "Baguete"
    assert "undeclared_secret" not in fields
    assert all(value == "" for name, value in fields.items() if name not in {
        "product_name", "product_label", "customer_name_greeting",
    })


@override_settings(DEBUG=False)
def test_a_personal_link_without_public_twin_is_cleared_not_kept_from_before(provider, flows, open_mode):
    assert mc.send(
        "+5543999990001",
        "stock_arrived",
        {"action_url": "https://loja.example/a?t=token-pessoal"},
    ) is True

    assert _last_fields(provider)["action_url"] == ""


@override_settings(DEBUG=False)
def test_order_flows_keep_writing_only_what_they_have(provider, flows):
    assert mc.send("+5543999990001", "order_accepted", {"order_ref": "PED-1"}) is True

    fields = _last_fields(provider)
    assert fields["order_ref"] == "PED-1"
    assert "price" not in fields
    assert all(value != "" for value in fields.values())


def test_the_durable_adapter_fills_every_sealed_campaign_variable_the_flow_declares():
    from shopman.shop.adapters.marketing_delivery_whatsapp import SEALED_VARIABLES
    from shopman.shop.services.campaign import available_variables

    declared = set(safety.MARKETING_FLOW_FIELDS["announcement_published"])
    assert set(SEALED_VARIABLES) <= declared
    # Tudo o que o gestor pode escrever num modelo tem de onde sair no envio durável:
    # das variáveis seladas, do link resolvido ou do destino (nome do cliente).
    assert set(available_variables()) <= set(SEALED_VARIABLES) | {"link", "customer_name"}


def test_declared_sets_cover_exactly_the_marketing_events_and_the_campaign_vocabulary():
    from shopman.shop.services.campaign import available_variables

    assert set(safety.MARKETING_FLOW_FIELDS) == set(safety.MARKETING_FLOW_EVENTS)
    announcement = set(safety.MARKETING_FLOW_FIELDS["announcement_published"])
    assert set(available_variables()) <= announcement
    assert {"body", "cta", "action_url"} <= announcement
    for fields in safety.MARKETING_FLOW_FIELDS.values():
        assert not set(fields) & mc._FIELD_DENYLIST


# ── 2. Modos ─────────────────────────────────────────────────────────


def test_blocked_is_the_default_state():
    state = safety.safety_state()

    assert state.state == "blocked_unverified"
    assert state.allows_delivery is False
    assert state.reason_code == "manychat_custom_fields_unverified"


@override_settings(SHOPMAN_MARKETING_WHATSAPP_MODE="opne")
def test_unknown_mode_counts_as_blocked(shared_cache):
    assert safety.safety_state().state == "blocked_unverified"


@override_settings(DEBUG=False)
@pytest.mark.parametrize("event", sorted(safety.MARKETING_FLOW_EVENTS))
def test_blocked_blocks_every_marketing_event_even_for_a_listed_ref(settings, provider, flows, shared_cache, event):
    settings.SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS = (LISTED,)

    assert mc.send("+5543999990001", event, {"customer_ref": LISTED}) is False
    assert provider == []


@override_settings(DEBUG=False)
@pytest.mark.parametrize("event", sorted(safety.MARKETING_FLOW_EVENTS))
def test_canary_lets_only_the_listed_ref_through(provider, flows, canary_mode, event):
    assert mc.send("+5543999990001", event, {"customer_ref": LISTED, "product_name": "Baguete"}) is True
    assert _flow_sends(provider) == 1
    fields = {p["field_name"] for e, p in provider if e.endswith("setCustomFieldByName")}
    assert "customer_ref" not in fields, "o ref do ensaio não pode virar campo no ManyChat"


@override_settings(DEBUG=False)
@pytest.mark.parametrize("event", sorted(safety.MARKETING_FLOW_EVENTS))
def test_canary_blocks_another_ref_and_the_anonymous_subscriber(provider, flows, canary_mode, event):
    assert mc.send("+5543999990001", event, {"customer_ref": "CLI-OUTRO"}) is False
    assert mc.send("+5543999990001", event, {"customer_ref": ""}) is False
    assert mc.send("+5543999990001", event, {}) is False
    assert provider == []


def test_canary_state_says_how_many_never_who(canary_mode, settings):
    settings.SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS = "CLI-A, CLI-B ,,"

    state = safety.safety_state()

    assert state.state == "canary"
    assert state.allows_delivery is True
    assert state.safe is False
    assert state.canary_size == 2
    assert "CLI-A" not in repr((state.reason, state.action))
    safety.require_safe_delivery()  # a aprovação não recusa o ensaio


@override_settings(DEBUG=False)
def test_canary_without_a_list_is_blocked(settings, provider, flows, shared_cache):
    settings.SHOPMAN_MARKETING_WHATSAPP_MODE = "canary"
    settings.SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS = ()

    state = safety.safety_state()

    assert state.state == "blocked_unverified"
    assert state.reason_code == "manychat_canary_contacts_missing"
    assert mc.send("+5543999990001", "announcement_published", {"customer_ref": LISTED}) is False
    assert provider == []
    with pytest.raises(MarketingContractError) as caught:
        safety.require_safe_delivery()
    assert caught.value.code == "manychat_canary_contacts_missing"


@override_settings(DEBUG=False, SHOPMAN_MARKETING_WHATSAPP_MODE="open")
def test_open_with_a_process_local_cache_is_blocked(provider, flows):
    """A suíte roda com LocMem: é exatamente o cache que NÃO serializa entre processos."""
    assert safety.serialization_available() is False

    state = safety.safety_state()

    assert state.state == "blocked_unverified"
    assert state.reason_code == "manychat_flow_serialization_unavailable"
    assert mc.send("+5543999990001", "announcement_published", {"customer_ref": LISTED}) is False
    assert provider == []


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": "redis://x"}})
def test_redis_counts_as_shared_and_locmem_dummy_do_not():
    assert safety.serialization_available() is True
    with override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}):
        assert safety.serialization_available() is False


def test_open_with_shared_cache_is_safe(open_mode):
    state = safety.safety_state()

    assert state.state == "safe"
    assert state.safe is True
    assert safety.recipient_refusal("") == ""


@override_settings(SHOPMAN_MANYCHAT_FLOW_SETTLE_SECONDS=0)
def test_a_zero_window_falls_back_to_the_default():
    assert safety.flow_settle_seconds() == 120


# ── 3. Check de deploy: Warning, nunca Error ─────────────────────────


def test_blocked_mode_has_no_isolation_warning():
    assert check_marketing_whatsapp_isolation(None) == []


@override_settings(SHOPMAN_MARKETING_WHATSAPP_MODE="open")
def test_open_with_local_cache_warns_without_blocking_deploy():
    (warning,) = check_marketing_whatsapp_isolation(None)

    assert warning.id == "SHOPMAN_W021"
    assert type(warning).__name__ == "Warning"
    assert "cache" in warning.msg


@override_settings(SHOPMAN_MARKETING_WHATSAPP_MODE="canary", SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS=())
def test_canary_without_list_warns(shared_cache):
    (warning,) = check_marketing_whatsapp_isolation(None)

    assert warning.id == "SHOPMAN_W021"
    assert type(warning).__name__ == "Warning"
    assert "CANARY_CUSTOMER_REFS" in warning.msg


@override_settings(SHOPMAN_MARKETING_WHATSAPP_MODE="opne")
def test_unknown_mode_warns():
    (warning,) = check_marketing_whatsapp_isolation(None)

    assert type(warning).__name__ == "Warning"
    assert "opne" in warning.msg


def test_healthy_canary_has_no_isolation_warning(canary_mode):
    assert check_marketing_whatsapp_isolation(None) == []


# ── 4. Tela: a prontidão diz "ensaio", nunca "pronto para todos" ─────


def test_readiness_in_canary_is_limited_and_counts_the_contacts(canary_mode, settings, monkeypatch):
    from shopman.shop.services import delivery_readiness as dr
    from shopman.shop.services.manychat_flows import FlowCatalog

    settings.SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED = True
    settings.SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED = True
    settings.SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS = (LISTED, "CLI-B")
    monkeypatch.setattr("shopman.shop.handlers.campaign._whatsapp_backend", lambda: "manychat")
    durable = type("A", (), {"is_available": staticmethod(lambda: True)})()
    monkeypatch.setattr(
        "shopman.shop.services.marketing_delivery_runtime.delivery_provider",
        lambda platform, require_available=False: durable if platform == "whatsapp" else None,
    )
    NotificationTemplate.objects.create(
        event="announcement_published", subject="x", body="y", whatsapp_flow_ns="content_ok",
    )
    now = timezone.now()
    monkeypatch.setattr(
        "shopman.shop.services.manychat_flows.flow_catalog",
        lambda **kwargs: FlowCatalog(
            flows=(("content_ok", "Anúncio"),),
            state="fresh",
            checked_at=now,
            facts_as_of=now,
            fresh_until=now + timedelta(minutes=5),
            catalog_hash="a" * 64,
            reason_code="",
        ),
    )

    (state,) = dr.readiness_for(["whatsapp"])

    assert state.state == "degraded"
    assert state.ready is True
    assert state.reason_code == "whatsapp_canary_active"
    assert state.canary_recipients == 2
    assert state.limitation.startswith("Ensaio: só 2 contatos recebem.")
    assert LISTED not in state.limitation


# ── 5. Campanha legada: ocupado reagenda só quem estava ocupado ──────


class _Manychat:
    """Transporte registrado como `manychat`, com resultado programado por telefone."""

    def __init__(self, results: dict[str, object]):
        self.results = results
        self.sent: list[dict] = []

    def is_available(self, *a, **kw) -> bool:
        return True

    def send(self, **kwargs):
        self.sent.append(kwargs)
        return self.results.get(kwargs["recipient"], True)


def _recipient(ref: str, phone: str):
    return SimpleNamespace(phone=phone, customer_ref=ref, customer_uuid="", first_name="Ana")


def _wave_announcement():
    return SimpleNamespace(
        pk=91, body="Saiu do forno!", content={"link": "", "variables": {}}, expires_at=None,
    )


def test_legacy_wave_does_not_count_busy_as_failure_and_reports_the_ref(monkeypatch):
    from shopman.shop.handlers import campaign as handlers

    transport = _Manychat({"+5543999990002": {"success": False, "error": "subscriber_busy", "retry_after_seconds": 120}})
    monkeypatch.setattr(notifications, "_adapters", {"manychat": transport})
    busy: list[str] = []

    sent, failed = handlers._send_to(
        (_recipient("CLI-A", "+5543999990001"), _recipient("CLI-B", "+5543999990002")),
        announcement=_wave_announcement(),
        busy_refs=busy,
    )

    assert (sent, failed) == (1, 0)
    assert busy == ["CLI-B"]
    assert transport.sent[0]["context"]["customer_ref"] == "CLI-A"


def test_legacy_handler_requeues_only_the_busy_refs_after_the_window(monkeypatch):
    from shopman.orderman.models import Directive

    from shopman.shop.handlers import campaign as handlers
    from shopman.shop.models import Announcement, AnnouncementStatus, AnnouncementTemplate, Campaign

    template = AnnouncementTemplate.objects.create(name="T-busy", body="Novidade")
    rule = Campaign.objects.create(
        name="Busy", trigger="manual", template=template, platforms=["whatsapp"],
        audience_rules={"favorites": True},
    )
    announcement = Announcement.objects.create(
        rule=rule, template=template, status=AnnouncementStatus.PUBLISHING,
        content={"body": "Novidade"}, platforms=["whatsapp"],
    )
    recipients = (_recipient("CLI-A", "+5543999990001"), _recipient("CLI-B", "+5543999990002"))
    monkeypatch.setattr("shopman.shop.services.audience.select_wave", lambda *a, **k: recipients)
    transport = _Manychat({"+5543999990002": {"success": False, "error": "subscriber_busy", "retry_after_seconds": 120}})
    monkeypatch.setattr(notifications, "_adapters", {"manychat": transport})
    before = timezone.now()

    handlers.AnnouncementNotifyHandler().handle(
        message=SimpleNamespace(pk=555, payload={"announcement_id": announcement.pk, "wave": "all"}),
        ctx={},
    )

    retry = Directive.objects.get(topic="announcement.notify")
    assert retry.payload["only_customer_refs"] == ["CLI-B"]
    assert retry.available_at >= before + timedelta(seconds=120)
    announcement.refresh_from_db()
    assert announcement.platform_results["whatsapp"]["sent"] == 1
    assert announcement.platform_results["whatsapp"]["failed"] == 0

    # A directive de reenvio alcança SÓ quem estava ocupado.
    transport.results = {}
    transport.sent.clear()
    handlers.AnnouncementNotifyHandler().handle(message=retry, ctx={})
    assert [call["recipient"] for call in transport.sent] == ["+5543999990002"]


def test_legacy_wave_in_canary_only_tries_the_listed_contact(monkeypatch, canary_mode):
    from shopman.shop.handlers import campaign as handlers

    transport = _Manychat({})
    monkeypatch.setattr(notifications, "_adapters", {"manychat": transport})

    sent, failed = handlers._send_to(
        (_recipient(LISTED, "+5543999990001"), _recipient("CLI-OUTRO", "+5543999990002"),
         SimpleNamespace(phone="+5543999990003")),
        announcement=_wave_announcement(),
    )

    assert (sent, failed) == (1, 0)
    assert [call["recipient"] for call in transport.sent] == ["+5543999990001"]


# ── 6. Ledger durável: ocupado volta à fila depois da janela ─────────


class _BusyProvider:
    def __init__(self):
        self.calls = 0

    def send(self, **_kwargs):
        self.calls += 1
        raise ProviderCallFailure(
            kind=ProviderOutcomeKind.NOT_ATTEMPTED,
            code="subscriber_busy",
            retry_after_seconds=120,
        )


class _AcceptingProvider:
    def __init__(self):
        self.calls = 0

    def send(self, **_kwargs):
        self.calls += 1
        return ProviderOutcome(
            kind=ProviderOutcomeKind.ACCEPTED_UNCONFIRMED,
            code="provider_accepted",
            retryable=False,
            provider_receipt_ref="fake_after_window",
        )


def test_ledger_busy_is_deferred_past_the_window_and_reuses_the_same_attempt():
    from shopman.shop.services.marketing_delivery_attempts import (
        deterministic_attempt_token,
        execute_target,
    )
    from shopman.shop.services.marketing_delivery_worker import claim_due_targets
    from shopman.shop.tests.test_marketing_delivery_worker import (
        _artifact,
        _fanout_whatsapp,
        _next_allowed_time,
        _queue_all,
    )

    outbox, _members, _report = _fanout_whatsapp(suffix="flow-busy", count=1, opted_in=True)
    _queue_all(outbox)
    clock = _next_allowed_time()
    worker = "worker-flow-busy"
    (target,) = claim_due_targets(worker_id=worker, now=clock).targets
    artifact = _artifact("whatsapp")
    token = deterministic_attempt_token(target.ref, worker_id=worker, now=clock)

    busy = execute_target(
        target.ref, provider=_BusyProvider(), artifact=artifact, idempotency_token=token,
        request_hash=artifact.artifact_hash, worker_id=worker, now=clock,
    )

    assert busy.provider_called is False
    assert busy.target.state == DeliveryTarget.State.QUEUED
    assert busy.target.last_error_code == "subscriber_busy"
    assert busy.target.next_attempt_at >= clock + timedelta(seconds=120)
    assert busy.attempt.state == DeliveryAttempt.State.PREPARED
    assert busy.target.state != DeliveryTarget.State.FAILED_RETRYABLE

    assert claim_due_targets(worker_id=worker, now=clock + timedelta(seconds=119)).targets == ()
    later = clock + timedelta(seconds=121)
    (again,) = claim_due_targets(worker_id=worker, now=later).targets
    assert deterministic_attempt_token(again.ref, worker_id=worker, now=later) == token

    accepted = execute_target(
        again.ref, provider=_AcceptingProvider(), artifact=artifact, idempotency_token=token,
        request_hash=artifact.artifact_hash, worker_id=worker, now=later,
    )

    assert accepted.target.state == DeliveryTarget.State.ACCEPTED
    assert DeliveryAttempt.objects.filter(target=accepted.target).count() == 1


def test_ledger_claim_in_canary_suppresses_whoever_is_outside_the_list(settings, shared_cache):
    from shopman.shop.services.marketing_delivery_worker import claim_due_targets
    from shopman.shop.tests.test_marketing_delivery_worker import (
        _fanout_whatsapp,
        _next_allowed_time,
        _queue_all,
    )

    outbox, members, _report = _fanout_whatsapp(suffix="flow-canary", count=2, opted_in=True)
    settings.SHOPMAN_MARKETING_WHATSAPP_MODE = "canary"
    settings.SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS = (members[0].customer.ref,)
    _queue_all(outbox)

    report = claim_due_targets(worker_id="worker-flow-canary", now=_next_allowed_time())

    assert len(report.targets) == 1
    assert report.targets[0].member_id == members[0].pk
    outsider = DeliveryTarget.objects.get(outbox=outbox, member=members[1])
    assert outsider.state == DeliveryTarget.State.SUPPRESSED
    assert outsider.last_error_code == "whatsapp_canary_recipient_excluded"
