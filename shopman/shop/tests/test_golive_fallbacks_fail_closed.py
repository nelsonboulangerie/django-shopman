"""Fallbacks que falhavam ABERTOS e calados, agora fechados ou gritando.

Inventário: docs/plans/fallbacks-perigosos-go-live.md, itens 1, 2, 9, 10, 12,
15 e 17. Cada teste abaixo falhava com o código anterior ao conserto.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.test import override_settings
from shopman.orderman.models import Directive

from config import settings as project_settings
from shopman.shop.adapters import _external, notification_manychat, notification_sms, notification_whatsapp

# ── 1 e 2: ambiente de cobrança e fiscal é decisão explícita em produção ──


def _load_settings(monkeypatch, **env):
    """Re-executa config/settings.py com a env controlada (sem o .env do disco)."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    for name in ("EFI_SANDBOX", "FOCUS_NFE_ENVIRONMENT", "DJANGO_DEBUG", "SHOPMAN_ENVIRONMENT", "SENTRY_DSN"):
        monkeypatch.delenv(name, raising=False)
    # DEBUG só para o boot não exigir o resto do perfil de produção (hosts,
    # banco, segredos); a lista é calculada igual em qualquer ambiente.
    monkeypatch.setenv("DJANGO_DEBUG", "true")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("shopman_settings_fallbacks", Path(project_settings.__file__))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_settings_lists_provider_environments_left_to_default(monkeypatch):
    loaded = _load_settings(monkeypatch, DJANGO_SECRET_KEY="segredo-de-teste")
    assert loaded.SHOPMAN_UNDECLARED_PROVIDER_ENVIRONMENTS == ("EFI_SANDBOX", "FOCUS_NFE_ENVIRONMENT")
    # O default de teste continua valendo para dev/staging: nada muda no alpha.
    assert loaded.SHOPMAN_EFI["sandbox"] is True
    assert loaded.SHOPMAN_FOCUS_NFE["environment"] == "homologacao"


def test_settings_counts_explicit_declaration_even_of_test_values(monkeypatch):
    loaded = _load_settings(
        monkeypatch,
        DJANGO_SECRET_KEY="segredo-de-teste",
        EFI_SANDBOX="true",
        FOCUS_NFE_ENVIRONMENT="homologacao",
    )
    assert loaded.SHOPMAN_UNDECLARED_PROVIDER_ENVIRONMENTS == ()


def test_settings_treats_empty_value_as_undeclared(monkeypatch):
    loaded = _load_settings(monkeypatch, DJANGO_SECRET_KEY="segredo-de-teste", EFI_SANDBOX="  ", FOCUS_NFE_ENVIRONMENT="producao")
    assert loaded.SHOPMAN_UNDECLARED_PROVIDER_ENVIRONMENTS == ("EFI_SANDBOX",)


def test_production_refuses_provider_environments_left_to_default(settings):
    from shopman.shop.checks import check_provider_environments_declared

    settings.SHOPMAN_ENVIRONMENT = "production"
    settings.SHOPMAN_UNDECLARED_PROVIDER_ENVIRONMENTS = ("EFI_SANDBOX", "FOCUS_NFE_ENVIRONMENT")
    errors = check_provider_environments_declared(None)
    assert [error.id for error in errors] == ["SHOPMAN_E026", "SHOPMAN_E026"]
    assert "EFI_SANDBOX" in errors[0].msg and "EFI_SANDBOX=false" in errors[0].hint
    assert "FOCUS_NFE_ENVIRONMENT" in errors[1].msg and "FOCUS_NFE_ENVIRONMENT=producao" in errors[1].hint


def test_production_with_both_declared_passes_this_gate(settings):
    from shopman.shop.checks import check_provider_environments_declared

    settings.SHOPMAN_ENVIRONMENT = "production"
    settings.SHOPMAN_UNDECLARED_PROVIDER_ENVIRONMENTS = ()
    assert check_provider_environments_declared(None) == []


@pytest.mark.parametrize("environment", ["staging", "development"])
def test_non_production_keeps_the_test_defaults(settings, environment):
    from shopman.shop.checks import check_provider_environments_declared

    settings.SHOPMAN_ENVIRONMENT = environment
    settings.SHOPMAN_UNDECLARED_PROVIDER_ENVIRONMENTS = ("EFI_SANDBOX", "FOCUS_NFE_ENVIRONMENT")
    assert check_provider_environments_declared(None) == []


def test_production_template_declares_efi_sandbox_false():
    import yaml

    spec = yaml.safe_load((Path(project_settings.__file__).resolve().parents[1] / ".do" / "app.subdomains.yaml").read_text())
    envs = {item["key"]: item.get("value") for item in spec.get("envs", [])}
    assert envs.get("EFI_SANDBOX") == "false"
    assert "FOCUS_NFE_ENVIRONMENT" in envs


# ── 9 e 10: config de estoque ilegível ───────────────────────────────


def _order(ref="FB-1", channel_ref="web"):
    return SimpleNamespace(ref=ref, channel_ref=channel_ref)


def _break_channel_config(monkeypatch):
    from shopman.shop.config import ChannelConfig

    def boom(cls, channel_ref):
        raise ValueError("config ilegível")

    monkeypatch.setattr(ChannelConfig, "for_channel", classmethod(boom))


@pytest.mark.django_db
def test_unreadable_config_refuses_untracked_sku_and_alerts(monkeypatch):
    from shopman.backstage.models import OperatorAlert
    from shopman.shop.services.stock import _channel_allows_untracked

    _break_channel_config(monkeypatch)
    # Antes: devolvia o default permissivo (True), calado: SKU fora do catálogo
    # virava pedido sem reserva justamente quando a config não respondia.
    assert _channel_allows_untracked(_order()) is False
    alert = OperatorAlert.objects.get(type="integration_config_drift")
    assert "web" in alert.message and "FB-1" in alert.message


@pytest.mark.django_db
def test_unreadable_config_keeps_preorder_but_alerts(monkeypatch):
    from shopman.backstage.models import OperatorAlert
    from shopman.shop.services.stock import _channel_allows_preorder

    _break_channel_config(monkeypatch)
    # A venda não é recusada por um JSON quebrado (decisão registrada no
    # código), mas agora o operador fica sabendo.
    assert _channel_allows_preorder(_order()) is True
    assert OperatorAlert.objects.filter(type="integration_config_drift").count() == 1


# ── 12: Shop.integrations ilegível grita ─────────────────────────────


def test_unreadable_shop_integrations_logs_error(monkeypatch):
    from shopman.shop import adapters

    def boom(adapter_type):
        raise RuntimeError("db fora")

    seen = []
    monkeypatch.setattr(adapters, "_shop_integrations_value", boom)
    monkeypatch.setattr(adapters.logger, "error", lambda msg, *a, **k: seen.append(("error", msg)))
    monkeypatch.setattr(adapters.logger, "debug", lambda msg, *a, **k: seen.append(("debug", msg)))
    assert adapters._from_shop_integrations("payment", method="pix") == (None, False)
    # Antes: logger.debug, invisível em nível normal e fora do Sentry.
    assert [level for level, msg in seen if "shop_integrations_unreadable" in msg] == ["error"]


# ── 15: inerte não é entrega ─────────────────────────────────────────

COMTELE = {"api_key": "key-1", "route": "17", "timeout": 5}
MANYCHAT = {"api_token": "tok-1", "base_url": "https://api.manychat.com/fb", "timeout": 5}
WHATSAPP = {"PHONE_NUMBER_ID": "123", "ACCESS_TOKEN": "tok-1", "timeout": 5}


@override_settings(DEBUG=False, SHOPMAN_SMS=COMTELE, SHOPMAN_MANYCHAT=MANYCHAT, SHOPMAN_WHATSAPP=WHATSAPP)
def test_suppressed_process_never_reports_delivery(monkeypatch):
    monkeypatch.setattr(_external, "_suppressed_reason", "seed")
    assert notification_sms.send("+5543999990001", "order_accepted", {}) is False
    assert notification_manychat.send("5543999990001", "order_accepted", {}) is False
    assert notification_whatsapp.send("5543999990001", "order_accepted", {}) is False


@pytest.mark.django_db
def test_suppressed_process_records_skip_not_acceptance(monkeypatch):
    from shopman.shop.handlers.notification import NotificationSendHandler
    from shopman.shop.services import notification

    monkeypatch.setattr(_external, "_suppressed_reason", "seed")
    task = Directive.objects.create(
        topic=notification.TOPIC, payload={"order_ref": "NAO-EXISTE", "template": "order_accepted"}
    )
    # Nem "entregue" (a mentira de antes) nem retry (que o worker, não
    # suprimido, executaria de verdade para os telefones do seed).
    NotificationSendHandler().handle(message=task, ctx={})
    task.refresh_from_db()
    delivery = task.payload["notification_delivery"]
    assert delivery["status"] == "skipped"
    assert delivery["reason"] == "external_suppressed:seed"


# ── 17: chave de idempotência não é reusada no escuro ────────────────


def _break_payman_lookup(monkeypatch):
    import shopman.payman as payman

    class Broken:
        class objects:
            @staticmethod
            def filter(*args, **kwargs):
                raise RuntimeError("db fora")

    monkeypatch.setattr(payman, "PaymentIntent", Broken)


def test_failed_lookup_does_not_reuse_stored_key(monkeypatch):
    from shopman.shop.services.payment import PaymentAttemptLookupUnavailable, _payment_idempotency_key_reusable

    _break_payman_lookup(monkeypatch)
    # Antes: devolvia True, e o retry reusava uma chave talvez envenenada.
    with pytest.raises(PaymentAttemptLookupUnavailable):
        _payment_idempotency_key_reusable("order-payment:X:pix:100:g0", order=_order(), method="pix", amount_q=100)


def test_failed_generation_lookup_does_not_fall_back_to_first_key(monkeypatch):
    from shopman.shop.services.payment import PaymentAttemptLookupUnavailable, _burned_intent_generations

    _break_payman_lookup(monkeypatch)
    # Antes: devolvia 0, recalculando a chave da primeira tentativa (a que morreu).
    with pytest.raises(PaymentAttemptLookupUnavailable):
        _burned_intent_generations(_order(), method="pix")


@pytest.mark.django_db
def test_initiate_records_error_instead_of_charging_blind(monkeypatch):
    from shopman.orderman.models import Order

    from shopman.shop.services import payment

    order = Order.objects.create(
        ref="FB-PIX-1",
        channel_ref="web",
        status="new",
        total_q=1600,
        handle_type="phone",
        handle_ref="5543999990000",
        data={"payment": {"method": "pix"}},
    )

    def boom(*args, **kwargs):
        raise payment.PaymentAttemptLookupUnavailable(order.ref)

    created = []
    monkeypatch.setattr(payment, "_ensure_payment_idempotency_key", boom)

    class Adapter:
        __name__ = "shopman.shop.adapters.payment_mock"

        @staticmethod
        def create_intent(**kwargs):
            created.append(kwargs)
            raise AssertionError("não pode cobrar sem conferir as tentativas anteriores")

    monkeypatch.setattr(payment, "get_adapter", lambda *a, **k: Adapter)
    payment.initiate(order)
    order.refresh_from_db()
    assert created == []
    assert "conferir a cobrança anterior" in (order.data.get("payment") or {}).get("error", "")
