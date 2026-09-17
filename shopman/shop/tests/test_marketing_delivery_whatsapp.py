"""Entrega durável de campanha por WhatsApp — o adapter que faltava no ledger.

Antes deste adapter, ``SHOPMAN_MARKETING_DELIVERY_ADAPTERS`` só registrava as plataformas
de postagem pública: campanha de WhatsApp aprovada no cockpit ficava na fila, em
qualquer ambiente. Estes testes montam o grafo REAL (aprovação → outbox → directive →
ledger → tentativa → adapter) e trocam só o fim da linha: a chamada HTTP ao ManyChat.

O que eles travam:

- o modo ``blocked``/``canary`` decide na última porta, sem chamar o provedor;
- contato ocupado volta pelo reagendamento do ledger, nunca vira falha nem ``unknown``;
- aceite do ManyChat é ``accepted_unconfirmed``; erro depois de possível escrita é
  ``unknown``; recusa antes de chamar é ``failed_final`` com código;
- as variáveis do flow saem do artefato selado — mexer no produto vivo depois da
  aprovação não muda a mensagem;
- consentimento, opt-out e maioridade são revalidados no caminho do WhatsApp.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from shopman.guestman import ConsentService
from shopman.guestman.models import Customer
from shopman.offerman.models import Product
from shopman.orderman.models import Directive

from shopman.shop.adapters import marketing_delivery_whatsapp as whatsapp
from shopman.shop.adapters import notification_manychat as mc
from shopman.shop.handlers.campaign import AnnouncementNotifyHandler
from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AnnouncementTemplate,
    Campaign,
    DeliveryAttempt,
    DeliveryTarget,
    MarketingOutbox,
    NotificationTemplate,
)
from shopman.shop.services import campaign as campaign_service
from shopman.shop.services import manychat_marketing_safety as safety
from shopman.shop.services import marketing_outbox
from shopman.shop.services.marketing_approval import PUBLISH_NOW, approve_command
from shopman.shop.services.marketing_delivery_attempts import (
    deterministic_attempt_token,
    execute_approved_target,
)
from shopman.shop.services.marketing_delivery_runtime import delivery_provider
from shopman.shop.services.marketing_delivery_worker import claim_due_targets

pytestmark = pytest.mark.django_db

SUBSCRIBER = 5151
FLOW = "content_campanha_whatsapp"
SKU = "BE"
AUDIENCE = 10  # Público de trabalho; o mínimo configurável no Admin é a seção 6.
WORKER = "whatsapp-delivery-test"


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def platform(settings, monkeypatch):
    """Plataforma ligada como no ensaio: flag, adapter registrado, Redis, ManyChat."""

    settings.DEBUG = False
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://loja.example"
    settings.SHOPMAN_MARKETING_MEDIA_HOSTS = ("loja.example",)
    settings.SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED = True
    settings.SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED = True
    settings.SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED = True
    settings.SHOPMAN_MARKETING_DELIVERY_ADAPTERS = {
        "whatsapp": "shopman.shop.adapters.marketing_delivery_whatsapp",
    }
    # A suíte usa LocMem; aqui ele faz o papel do Redis (um processo só).
    monkeypatch.setattr(safety, "serialization_available", lambda: True)
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def manychat(monkeypatch):
    """ManyChat de mentira: registra cada chamada HTTP, sem rede."""

    calls: list[tuple[str, dict]] = []
    responses: dict[str, dict] = {}

    def _fake(endpoint, payload, config):
        calls.append((endpoint, payload))
        for suffix, response in responses.items():
            if endpoint.endswith(suffix):
                return response
        return {"success": True}

    monkeypatch.setattr(mc, "_api_call", _fake)
    monkeypatch.setattr(mc, "_get_config", lambda: {"api_token": "synthetic", "flow_map": {}})
    monkeypatch.setattr(mc, "_resolve_subscriber", lambda *a, **k: SUBSCRIBER)
    return calls, responses


@pytest.fixture
def campaign(settings, monkeypatch):
    """A campanha do dono: favoritos da Baguete Gergelim, aprovada pelo cockpit."""

    return _approved_campaign(settings, monkeypatch, audience=AUDIENCE)


def _approved_campaign(settings, monkeypatch, *, audience: int, mode: str = "canary"):
    clock = _business_time()
    product = Product.objects.create(
        sku=SKU,
        name="Baguete Gergelim",
        base_price_q=1200,
        is_published=True,
        is_sellable=True,
        image_url="/media/baguete-gergelim.jpg",
    )
    customers = []
    for number in range(audience):
        customer = Customer.objects.create(
            ref=f"WA-DELIVERY-{number}",
            first_name=f"Pessoa{number}",
            phone=f"+55439987{number:05d}",
            birthday=date(1990, 1, 1),
        )
        ConsentService.grant_consent(customer.ref, "whatsapp", source="whatsapp-delivery-test")
        customers.append(customer)

    template = AnnouncementTemplate.objects.create(
        name="Testando o app de Mkt",
        body="{{product_name}} saiu do forno por {{price}}.",
    )
    rule = Campaign.objects.create(
        name="Testando o app de Mkt",
        trigger="manual",
        template=template,
        platforms=["whatsapp"],
        audience_rules={"customer_refs": [customer.ref for customer in customers]},
    )
    content = campaign_service.resolve_content(template, {"sku": SKU})
    announcement = Announcement.objects.create(
        rule=rule,
        template=template,
        status=AnnouncementStatus.PENDING_REVIEW,
        content=content,
        platform_content={},
        platforms=["whatsapp"],
        trigger_context={"sku": SKU},
    )
    NotificationTemplate.objects.create(
        event="announcement_published",
        subject="x",
        body="y",
        whatsapp_flow_ns=FLOW,
        version=3,
    )
    from shopman.shop.services.manychat_flows import FlowCatalog

    monkeypatch.setattr(
        "shopman.shop.services.manychat_flows.flow_catalog",
        lambda **kwargs: FlowCatalog(
            flows=((FLOW, "Campanha geral"),),
            state="fresh",
            checked_at=clock,
            facts_as_of=clock,
            fresh_until=clock + timedelta(minutes=5),
            catalog_hash="c" * 64,
        ),
    )
    # O ensaio aprovado: um contato só recebe.
    settings.SHOPMAN_MARKETING_WHATSAPP_MODE = mode
    settings.SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS = (customers[0].ref,)

    approved = approve_command(
        announcement.pk,
        actor=get_user_model().objects.create_user(username="whatsapp-delivery-operator"),
        idempotency_key="whatsapp-delivery-approval-0001",
        base_version=1,
        publish_mode=PUBLISH_NOW,
        content=content,
        platform_content={},
        platforms=["whatsapp"],
        now=clock,
    )
    return {
        "announcement": announcement,
        "approved": approved,
        "clock": clock,
        "customers": customers,
        "product": product,
    }


def _business_time() -> datetime:
    local = datetime.now(ZoneInfo("America/Sao_Paulo")) + timedelta(days=1)
    return local.replace(hour=10, minute=0, second=0, microsecond=0)


def _stage(campaign) -> MarketingOutbox:
    """outbox → directive → handler de produção → ledger enfileirado."""

    clock = campaign["clock"]
    report = marketing_outbox.process_due(worker_id="whatsapp-outbox-test", now=clock)
    assert report.dispatched == 1
    outbox = MarketingOutbox.objects.get(command=campaign["approved"].receipt)
    directive = Directive.objects.get(dedupe_key=f"marketing-outbox:{outbox.ref}")
    AnnouncementNotifyHandler().handle(message=directive, ctx={})
    return outbox


def _claim(campaign):
    return claim_due_targets(worker_id=WORKER, now=campaign["clock"])


def _execute(campaign, target, *, provider=whatsapp):
    clock = campaign["clock"]
    token = deterministic_attempt_token(target.ref, worker_id=WORKER, now=clock)
    return execute_approved_target(
        target.ref,
        provider=provider,
        idempotency_token=token,
        worker_id=WORKER,
        now=clock,
    )


def _fields(calls) -> dict[str, str]:
    return {
        payload["field_name"]: payload["field_value"]
        for endpoint, payload in calls
        if endpoint.endswith("setCustomFieldByName")
    }


def _flow_sends(calls) -> int:
    return sum(1 for endpoint, _payload in calls if endpoint.endswith("sendFlow"))


def _listed_target(campaign) -> DeliveryTarget:
    (target,) = _claim(campaign).targets
    assert target.member.customer_id == campaign["customers"][0].pk
    return target


# ── Ponta a ponta ────────────────────────────────────────────────────


def test_campaign_reaches_manychat_through_approval_outbox_ledger_and_adapter(manychat, campaign):
    calls, _responses = manychat

    outbox = _stage(campaign)
    claims = _claim(campaign)

    assert outbox.platform == "whatsapp"
    assert DeliveryTarget.objects.filter(outbox=outbox).count() == AUDIENCE
    assert len(claims.targets) == 1
    assert claims.suppressed == AUDIENCE - 1
    assert set(
        DeliveryTarget.objects.filter(outbox=outbox, state=DeliveryTarget.State.SUPPRESSED)
        .values_list("last_error_code", flat=True)
    ) == {safety.CANARY_RECIPIENT_EXCLUDED_CODE}

    execution = _execute(campaign, claims.targets[0])

    assert execution.provider_called is True
    assert execution.attempt.outcome_kind == "accepted_unconfirmed"
    assert execution.target.state == DeliveryTarget.State.ACCEPTED
    assert _flow_sends(calls) == 1
    (flow_call,) = [payload for endpoint, payload in calls if endpoint.endswith("sendFlow")]
    assert flow_call["subscriber_id"] == SUBSCRIBER
    assert flow_call["flow_ns"] == FLOW
    assert _claim(campaign).targets == ()


def test_the_maintenance_worker_pass_delivers_the_approved_campaign_once(
    manychat, campaign, monkeypatch
):
    """A entrega não tem componente próprio: a passada do `maintenance_worker` entrega.

    Roda a entrada EXATA da lista do worker (as mesmas opções que o alpha usa), não um
    `--watch` de laboratório. Rodar de novo no ciclo seguinte não chama o provedor.
    """
    from io import StringIO

    from django.core.management import call_command

    from shopman.shop.management.commands.maintenance_worker import MAINTENANCE_COMMANDS

    calls, _responses = manychat
    outbox = _stage(campaign)
    (entry,) = [
        e for e in MAINTENANCE_COMMANDS
        if isinstance(e, tuple) and e[0] == "process_marketing_delivery"
    ]
    command, options = entry
    monkeypatch.setattr(
        "shopman.shop.management.commands.process_marketing_delivery.timezone.now",
        lambda: campaign["clock"],
    )

    call_command(command, stdout=StringIO(), **options)

    assert _flow_sends(calls) == 1
    (accepted,) = DeliveryTarget.objects.filter(
        outbox=outbox, state=DeliveryTarget.State.ACCEPTED
    )
    assert accepted.member.customer_id == campaign["customers"][0].pk
    assert DeliveryAttempt.objects.filter(target=accepted).count() == 1

    call_command(command, stdout=StringIO(), **options)

    assert _flow_sends(calls) == 1


def test_registered_adapter_turns_the_missing_provider_into_the_canary_readiness(manychat, campaign):
    from shopman.shop.services.delivery_readiness import readiness_for

    with_adapter = readiness_for(["whatsapp"], now=campaign["clock"])[0]

    assert with_adapter.reason_code == "whatsapp_canary_active"
    assert with_adapter.state == "degraded"
    assert with_adapter.canary_recipients == 1


def _boot_settings(monkeypatch, **env):
    """Re-executa ``config/settings.py`` com a env controlada (o boot real)."""

    import importlib.util
    from pathlib import Path

    from config import settings as project_settings

    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    monkeypatch.delenv("SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED", raising=False)
    monkeypatch.setenv("DJANGO_DEBUG", "true")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location(
        "shopman_settings_whatsapp_delivery", Path(project_settings.__file__)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_boot_registers_the_whatsapp_adapter_only_behind_the_platform_flag(monkeypatch):
    default = _boot_settings(monkeypatch)
    enabled = _boot_settings(monkeypatch, SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED="true")

    assert default.SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED is False
    assert "whatsapp" not in default.SHOPMAN_MARKETING_DELIVERY_ADAPTERS
    assert enabled.SHOPMAN_MARKETING_DELIVERY_ADAPTERS["whatsapp"] == (
        "shopman.shop.adapters.marketing_delivery_whatsapp"
    )


def test_each_platform_switch_registers_exactly_its_own_platform(monkeypatch):
    """`PLATFORM_SWITCHES` é o que a prontidão cita como "desligada (flag X)".

    Se a flag citada não for a que registra o adapter no boot, a tela manda ligar
    a flag errada.
    """
    from shopman.shop.services.marketing_delivery_runtime import PLATFORM_SWITCHES

    # TikTok não está no catálogo selecionável; a flag dele fica desligada aqui.
    for switch in (*PLATFORM_SWITCHES.values(), "SHOPMAN_MARKETING_TIKTOK_PUBLICATION_ENABLED"):
        monkeypatch.delenv(switch, raising=False)
    assert set(_boot_settings(monkeypatch).SHOPMAN_MARKETING_DELIVERY_ADAPTERS) == set()
    for platform, switch in PLATFORM_SWITCHES.items():
        booted = _boot_settings(monkeypatch, **{switch: "true"})
        monkeypatch.delenv(switch)
        assert set(booted.SHOPMAN_MARKETING_DELIVERY_ADAPTERS) == {platform}, switch


def test_demo_profile_keeps_the_whatsapp_lane_on_the_local_simulator():
    from config import settings_marketing_demo

    assert settings_marketing_demo.SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED is False
    assert settings_marketing_demo.SHOPMAN_MARKETING_DELIVERY_ADAPTERS["whatsapp"] == (
        "shopman.shop.adapters.marketing_delivery_console"
    )


def test_without_the_platform_flag_the_lane_has_no_available_provider(settings, campaign):
    settings.SHOPMAN_MARKETING_WHATSAPP_DELIVERY_ENABLED = False

    assert whatsapp.is_available() is False
    assert delivery_provider("whatsapp") is None


# ── 1. Modo: a última porta ──────────────────────────────────────────


def test_blocked_refuses_at_the_last_door_without_calling_the_provider(settings, manychat, campaign):
    calls, _responses = manychat
    _stage(campaign)
    target = _listed_target(campaign)
    settings.SHOPMAN_MARKETING_WHATSAPP_MODE = "blocked"

    execution = _execute(campaign, target)

    assert calls == []
    assert execution.target.state == DeliveryTarget.State.FAILED_FINAL
    assert execution.target.last_error_code == safety.BLOCK_CODE
    assert execution.attempt.outcome_kind == "failed_final"


def test_canary_refuses_whoever_left_the_list_between_claim_and_send(settings, manychat, campaign):
    calls, _responses = manychat
    customers = campaign["customers"]
    _stage(campaign)
    settings.SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS = (customers[0].ref, customers[1].ref)
    claimed = {target.member.customer_id: target for target in _claim(campaign).targets}
    assert set(claimed) == {customers[0].pk, customers[1].pk}
    settings.SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS = (customers[0].ref,)

    outsider = _execute(campaign, claimed[customers[1].pk])

    assert calls == []
    assert outsider.target.state == DeliveryTarget.State.FAILED_FINAL
    assert outsider.target.last_error_code == safety.CANARY_RECIPIENT_EXCLUDED_CODE

    listed = _execute(campaign, claimed[customers[0].pk])

    assert listed.target.state == DeliveryTarget.State.ACCEPTED
    assert _flow_sends(calls) == 1


# ── 2. Contato ocupado: o ledger reagenda ───────────────────────────


def test_busy_subscriber_returns_to_the_queue_after_the_window(manychat, campaign):
    calls, _responses = manychat
    _stage(campaign)
    target = _listed_target(campaign)
    cache.add(f"{safety.FLOW_RESERVATION_KEY_PREFIX}{SUBSCRIBER}", "stock_arrived:x", timeout=120)

    execution = _execute(campaign, target)

    assert calls == []
    assert execution.provider_called is False
    assert execution.target.state == DeliveryTarget.State.QUEUED
    assert execution.target.last_error_code == safety.SUBSCRIBER_BUSY_CODE
    assert execution.target.next_attempt_at >= campaign["clock"] + timedelta(seconds=120)
    assert execution.attempt.state == DeliveryAttempt.State.PREPARED


# ── 3. Resultado honesto ─────────────────────────────────────────────


def test_manychat_acceptance_is_accepted_unconfirmed_never_delivered(manychat, campaign):
    _stage(campaign)

    execution = _execute(campaign, _listed_target(campaign))

    assert execution.attempt.outcome_kind == "accepted_unconfirmed"
    assert execution.attempt.error_code == whatsapp.ACCEPTED_CODE
    assert execution.target.state == DeliveryTarget.State.ACCEPTED
    assert execution.target.state != DeliveryTarget.State.CONFIRMED
    # Assinante não é recibo.
    assert execution.target.provider_receipt_ref == ""


def test_ambiguous_failure_after_the_fields_were_written_is_unknown(manychat, campaign):
    calls, responses = manychat
    responses["sendFlow"] = {
        "success": False,
        "error": "acceptance_unconfirmed",
        "outcome_unknown": True,
    }
    _stage(campaign)

    execution = _execute(campaign, _listed_target(campaign))

    assert _fields(calls), "os campos já tinham sido gravados quando a resposta se perdeu"
    assert execution.attempt.outcome_kind == "unknown"
    assert execution.target.state == DeliveryTarget.State.UNKNOWN
    assert execution.target.last_error_code == whatsapp.OUTCOME_UNKNOWN_CODE
    assert _claim(campaign).targets == ()


def test_explicit_provider_refusal_is_final_with_a_code(manychat, campaign):
    _calls, responses = manychat
    responses["sendFlow"] = {"success": False, "error": "provider_rejected"}
    _stage(campaign)

    execution = _execute(campaign, _listed_target(campaign))

    assert execution.target.state == DeliveryTarget.State.FAILED_FINAL
    assert execution.target.last_error_code == "whatsapp_provider_refused"


def test_flow_changed_after_approval_is_refused_before_the_provider(manychat, campaign):
    calls, _responses = manychat
    _stage(campaign)
    target = _listed_target(campaign)
    NotificationTemplate.objects.filter(event="announcement_published").update(
        whatsapp_flow_ns="content_outro_flow"
    )

    execution = _execute(campaign, target)

    assert calls == []
    assert execution.target.state == DeliveryTarget.State.FAILED_FINAL
    assert execution.target.last_error_code == "whatsapp_flow_changed_since_approval"


def test_lookup_never_invents_a_receipt():
    from shopman.shop.services.marketing_contracts import ProviderCallFailure

    with pytest.raises(ProviderCallFailure) as caught:
        whatsapp.lookup(target_key="a" * 64, idempotency_token="t" * 20, provider_receipt_ref="")

    assert caught.value.code == "whatsapp_lookup_unavailable"


# ── 4. O que a tela mostrou é o que sai ─────────────────────────────


def test_flow_variables_come_from_the_sealed_artifact_not_the_live_product(manychat, campaign):
    calls, _responses = manychat
    _stage(campaign)
    target = _listed_target(campaign)
    resolved = target.artifact.payload["resolved_artifacts"]["whatsapp"]
    product = campaign["product"]

    class ProductChangesAtTheLastSecond:
        """Muda o catálogo vivo DEPOIS da conferência de fatos, colado no envio."""

        @staticmethod
        def send(**kwargs):
            Product.objects.filter(pk=product.pk).update(name="Pão Trocado", base_price_q=99)
            return whatsapp.send(**kwargs)

    execution = _execute(campaign, target, provider=ProductChangesAtTheLastSecond)

    fields = _fields(calls)
    assert execution.target.state == DeliveryTarget.State.ACCEPTED
    assert resolved["body"] == "Baguete Gergelim saiu do forno por R$ 12,00."
    assert fields["body"] == resolved["body"]
    assert fields["product_name"] == "Baguete Gergelim"
    assert fields["price"] == "R$ 12,00"
    assert fields["product_sku"] == SKU
    assert fields["action_url"] == resolved["link"]
    assert fields["customer_name"] == campaign["customers"][0].first_name
    # Identificador interno e contato nunca viram campo no perfil do ManyChat.
    assert "customer_ref" not in fields
    assert "phone" not in fields
    assert campaign["customers"][0].phone not in fields.values()


def test_a_fact_that_changed_before_the_send_expires_the_target_and_nothing_goes_out(
    manychat, campaign
):
    calls, _responses = manychat
    _stage(campaign)
    Product.objects.filter(pk=campaign["product"].pk).update(base_price_q=1500)

    claims = _claim(campaign)

    assert claims.targets == ()
    assert calls == []
    assert set(
        DeliveryTarget.objects.filter(announcement=campaign["announcement"]).values_list(
            "state", flat=True
        )
    ) <= {DeliveryTarget.State.EXPIRED, DeliveryTarget.State.SUPPRESSED}


# ── 5. Revalidação no envio: consentimento, opt-out e maioridade ────


def test_opt_out_after_approval_is_suppressed_at_the_claim(manychat, campaign):
    calls, _responses = manychat
    listed = campaign["customers"][0]
    _stage(campaign)
    ConsentService.revoke_consent(listed.ref, "whatsapp", source="whatsapp-delivery-test")

    claims = _claim(campaign)

    assert claims.targets == ()
    assert calls == []
    target = DeliveryTarget.objects.get(
        announcement=campaign["announcement"], member__customer=listed
    )
    assert target.state == DeliveryTarget.State.SUPPRESSED
    assert target.last_error_code == "global_optout"


def test_opt_out_between_claim_and_send_is_refused_at_the_last_door(manychat, campaign):
    calls, _responses = manychat
    _stage(campaign)
    target = _listed_target(campaign)
    ConsentService.revoke_consent(
        campaign["customers"][0].ref, "whatsapp", source="whatsapp-delivery-test"
    )

    execution = _execute(campaign, target)

    assert calls == []
    assert execution.target.state == DeliveryTarget.State.FAILED_FINAL
    assert execution.target.last_error_code == "global_optout"


def test_age_proof_removed_between_claim_and_send_stops_before_the_adapter(manychat, campaign):
    calls, _responses = manychat
    _stage(campaign)
    target = _listed_target(campaign)
    Customer.objects.filter(pk=campaign["customers"][0].pk).update(birthday=None, metadata={})

    execution = _execute(campaign, target)

    assert calls == []
    assert execution.provider_called is False
    assert execution.target.state == DeliveryTarget.State.SUPPRESSED
    assert execution.target.last_error_code == "recipient_age_not_verified"


def test_minor_birthday_is_suppressed_at_the_claim(manychat, campaign):
    calls, _responses = manychat
    listed = campaign["customers"][0]
    _stage(campaign)
    minor = campaign["clock"].date().replace(year=campaign["clock"].year - 15)
    Customer.objects.filter(pk=listed.pk).update(birthday=minor)

    claims = _claim(campaign)

    assert claims.targets == ()
    assert calls == []
    target = DeliveryTarget.objects.get(
        announcement=campaign["announcement"], member__customer=listed
    )
    assert target.state == DeliveryTarget.State.SUPPRESSED
    assert target.last_error_code == "recipient_age_not_verified"


# ── 6. Mínimo configurável no Admin: vale fora do ensaio, não no ensaio ──


def _configure_minimum(value: int) -> None:
    """Grava a política como o Admin grava: ``Shop.defaults["marketing"]``."""
    from shopman.shop.models import Shop

    shop = Shop.objects.first() or Shop.objects.create(name="Nelson", brand_name="Nelson")
    shop.defaults = {**(shop.defaults or {}), "marketing": {"whatsapp_minimum_audience": value}}
    shop.save()


def test_canary_approves_an_audience_of_one_and_delivers_only_to_the_listed_ref(
    settings, monkeypatch, manychat
):
    """O alpha tem 5 contatos com WhatsApp autorizado: o mínimo tornava o ensaio impossível."""
    from shopman.backstage.projections.marketing_v2 import _safe_receipt_outcome
    from shopman.shop.models import MarketingAuditEvent

    calls, _responses = manychat
    _configure_minimum(3)
    campaign = _approved_campaign(settings, monkeypatch, audience=1, mode="canary")
    receipt = campaign["approved"].receipt

    assert receipt.outcome["audience_count"] == 1
    assert receipt.outcome["canary"] is True
    # O comprovante diz QUAL mínimo não valeu — o configurado, não um número escrito à mão.
    assert receipt.outcome["minimum_count"] == 3
    assert _safe_receipt_outcome(receipt.outcome)["canary"] is True
    assert _safe_receipt_outcome(receipt.outcome)["minimum_count"] == 3
    facts = MarketingAuditEvent.objects.get(command=receipt).facts
    assert facts["canary"] is True
    assert facts["minimum_count"] == 3

    _stage(campaign)
    (target,) = _claim(campaign).targets
    execution = _execute(campaign, target)

    assert target.member.customer_id == campaign["customers"][0].pk
    assert execution.target.state == DeliveryTarget.State.ACCEPTED
    assert _flow_sends(calls) == 1


@pytest.mark.parametrize("mode", ["open", "blocked"])
def test_outside_the_canary_the_configured_minimum_refuses_with_its_number(
    settings, monkeypatch, manychat, mode
):
    from shopman.shop.models import MarketingCommandReceipt
    from shopman.shop.services.marketing_commands import MarketingCommandRejected

    _configure_minimum(3)
    with pytest.raises(MarketingCommandRejected) as caught:
        _approved_campaign(settings, monkeypatch, audience=2, mode=mode)

    assert caught.value.code == "audience_below_minimum"
    assert "ao menos 3 pessoas elegíveis" in caught.value.detail
    receipt = MarketingCommandReceipt.objects.get(ref=caught.value.receipt_ref)
    assert receipt.outcome == {
        "code": "audience_below_minimum",
        "eligible_count": 2,
        "minimum_count": 3,
    }
    assert not MarketingOutbox.objects.exists()


def test_open_approval_at_the_configured_minimum_goes_through(settings, monkeypatch, manychat):
    _configure_minimum(3)

    campaign = _approved_campaign(settings, monkeypatch, audience=3, mode="open")

    assert campaign["approved"].receipt.outcome["audience_count"] == 3
    assert MarketingOutbox.objects.filter(command=campaign["approved"].receipt).count() == 1


def test_without_configuration_the_minimum_is_one(settings, monkeypatch, manychat):
    """Padrão do dono: começa em 1 para não segurar campanha boa no início da operação."""
    from shopman.shop.models import Shop

    assert not Shop.objects.exists()

    campaign = _approved_campaign(settings, monkeypatch, audience=1, mode="open")

    assert campaign["approved"].receipt.outcome["audience_count"] == 1
    assert "canary" not in campaign["approved"].receipt.outcome


def test_an_open_approval_at_the_minimum_does_not_claim_to_be_a_canary(
    settings, monkeypatch, manychat
):
    from shopman.shop.models import MarketingAuditEvent

    campaign = _approved_campaign(settings, monkeypatch, audience=AUDIENCE, mode="open")
    receipt = campaign["approved"].receipt

    assert receipt.outcome["audience_count"] == AUDIENCE
    assert "canary" not in receipt.outcome
    assert "canary" not in MarketingAuditEvent.objects.get(command=receipt).facts
