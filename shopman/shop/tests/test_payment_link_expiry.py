"""Validade do link de pagamento — o prazo segue o ciclo do atendimento.

O link é a cobrança do pedido remoto anotado no PDV. Enquanto nenhum prazo era
gravado, o único relógio era o do Stripe (24 h por conta própria) e ninguém aqui
o lia. A Frente 3 gravou um prazo — fixo, de 24 h — e o dono da casa reviu:
o pão é para hoje ou para amanhã, e a encomenda remota só é liberada contra o
pagamento; 24 h segurava estoque por um dia inteiro.

A regra agora é ``min(agora + janela do canal, corte do atendimento)``, presa à
régua do Stripe (30 min a 24 h − 1 min). Aqui se prova:

1. a régua (``_payment_link``): janela, corte, piso e teto;
2. o corte do atendimento (``services/payment_deadline``): início da janela
   combinada, fechamento da loja no dia do compromisso, e o silêncio quando
   não há expediente conhecido;
3. a janela como configuração de CANAL (``ChannelConfig.payment.link_timeout_minutes``),
   semeada no canal ``pdv`` e levada ao adapter pelo ``_adapter_config``;
4. os dois adapters que emitem link (Stripe e mock) gravando o MESMO instante
   no Payman e no gateway;
5. ``payment.initiate`` levando o prazo ao pedido e armando o ``payment.timeout``;
6. os dois predicados do lifecycle que o link vira: não é entrega de balcão, e
   exige captura antes do trabalho físico — mesmo no canal de ``timing="external"``.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings as django_settings
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Directive, Order
from shopman.payman.models import PaymentIntent as PaymanIntent

from shopman.shop import lifecycle
from shopman.shop.adapters import _payment_link, payment_mock, payment_stripe
from shopman.shop.config import ChannelConfig
from shopman.shop.directives import PAYMENT_TIMEOUT
from shopman.shop.models import Channel, Shop
from shopman.shop.services import payment as payment_service
from shopman.shop.services import payment_deadline
from shopman.shop.services.order_helpers import customer_holds_the_goods

pytestmark = pytest.mark.django_db

TZ = ZoneInfo("America/Sao_Paulo")

STRIPE_SETTINGS = {
    "secret_key": "sk_test_fake",
    "webhook_secret": "whsec_test_fake",
    "capture_method": "automatic",
    "domain": "https://shop.example.com",
}

MOCK_LINK_ADAPTERS = {
    "pix": "shopman.shop.adapters.payment_mock",
    "link": "shopman.shop.adapters.payment_mock",
    "cash": None,
    "external": None,
}

OPEN_9_TO_18 = {
    day: {"open": "09:00", "close": "18:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
}


def _local(*args) -> datetime:
    return datetime(*args, tzinfo=TZ)


def _shop(**overrides) -> Shop:
    cache.clear()
    fields = {"name": "Test Shop", "brand_name": "Test", "timezone": "America/Sao_Paulo", "opening_hours": OPEN_9_TO_18}
    fields.update(overrides)
    return Shop.objects.create(**fields)


def _order(**data) -> SimpleNamespace:
    return SimpleNamespace(ref="PDV-1", channel_ref="pdv", data={"origin_channel": "pos", **data})


def _stripe_double(session_id: str = "cs_test_link"):
    stripe = MagicMock()
    session = MagicMock()
    session.id = session_id
    session.url = f"https://checkout.stripe.com/c/pay/{session_id}"
    session.payment_intent = None
    stripe.checkout.Session.create.return_value = session
    return stripe


# ── 1. A régua: min(agora + janela, corte), presa ao Stripe ──────────────────


class TestLinkExpiresAt:
    NOW = _local(2026, 9, 2, 10, 0)  # quarta-feira

    def test_window_alone_when_there_is_no_cutoff(self):
        assert _payment_link.link_expires_at(self.NOW, timeout_minutes=120) == _local(2026, 9, 2, 12, 0)

    def test_cutoff_before_the_window_wins(self):
        """Retirada às 11h: o link não pode valer até meio-dia."""
        expires_at = _payment_link.link_expires_at(
            self.NOW, timeout_minutes=120, expires_by=_local(2026, 9, 2, 11, 0)
        )
        assert expires_at == _local(2026, 9, 2, 11, 0)

    def test_cutoff_after_the_window_is_ignored(self):
        """Encomenda para amanhã: a janela do canal é o teto, não o compromisso."""
        expires_at = _payment_link.link_expires_at(
            self.NOW, timeout_minutes=120, expires_by=_local(2026, 9, 3, 12, 0)
        )
        assert expires_at == _local(2026, 9, 2, 12, 0)

    @pytest.mark.parametrize(
        "cutoff",
        [
            _local(2026, 9, 2, 9, 0),  # já passou
            _local(2026, 9, 2, 10, 10),  # a menos de 30 min
        ],
    )
    def test_cutoff_too_close_falls_to_the_stripe_floor(self, cutoff):
        """Venda de link às 17h50 para retirar às 18h: vale o piso (30 min) e a
        casa aceita esse caso raro — recusar a venda com o cliente ao telefone
        seria pior, e o Stripe recusa qualquer coisa abaixo de 30 min."""
        expires_at = _payment_link.link_expires_at(self.NOW, timeout_minutes=120, expires_by=cutoff)
        assert expires_at == self.NOW + _payment_link.LINK_TTL_MIN

    def test_window_is_capped_at_the_stripe_ceiling(self):
        expires_at = _payment_link.link_expires_at(self.NOW, timeout_minutes=3 * 24 * 60)
        assert expires_at == self.NOW + _payment_link.LINK_TTL_MAX
        assert _payment_link.LINK_TTL_MAX == timedelta(hours=24) - timedelta(minutes=1)

    def test_window_below_the_floor_is_raised_to_it(self):
        assert _payment_link.link_expires_at(self.NOW, timeout_minutes=5) == self.NOW + _payment_link.LINK_TTL_MIN

    @pytest.mark.parametrize("raw", [None, "", "abc", 0, -15])
    def test_unusable_window_falls_back_to_the_channel_default(self, raw):
        """Config quebrada não derruba a venda: vale o default da ``ChannelConfig``."""
        assert _payment_link.link_window(raw) == _payment_link.default_link_timeout()

    def test_default_window_is_the_channel_config_default(self):
        """Um número só: o adapter sem config vence no mesmo prazo de um canal novo."""
        assert _payment_link.default_link_timeout() == timedelta(minutes=ChannelConfig.Payment.link_timeout_minutes)
        assert ChannelConfig.Payment.link_timeout_minutes == 120

    def test_expires_by_accepts_iso_and_datetime(self):
        iso = _local(2026, 9, 2, 11, 0).isoformat()
        assert _payment_link.parse_expires_by(iso) == _local(2026, 9, 2, 11, 0)
        assert _payment_link.parse_expires_by(_local(2026, 9, 2, 11, 0)) == _local(2026, 9, 2, 11, 0)

    def test_unreadable_expires_by_is_ignored(self):
        assert _payment_link.parse_expires_by("amanhã de manhã") is None
        assert _payment_link.link_expires_at(self.NOW, timeout_minutes=120, expires_by="amanhã de manhã") == _local(
            2026, 9, 2, 12, 0
        )

    def test_epoch_is_the_same_instant_in_stripe_vocabulary(self):
        expires_at = _payment_link.link_expires_at(self.NOW, timeout_minutes=120)
        assert _payment_link.link_expires_at_epoch(expires_at) == int(expires_at.timestamp())


# ── 2. O corte do atendimento ─────────────────────────────────────────────────


class TestServiceCutoff:
    NOW = _local(2026, 9, 2, 10, 0)  # quarta-feira, loja aberta

    def cutoff(self, order, *, shop=None, now=None):
        return payment_deadline.service_cutoff(order, now=now or self.NOW, shop=shop)

    def test_pickup_now_cuts_at_todays_closing(self):
        """Sem compromisso nenhum (retirada "agora"): o fechamento de hoje."""
        assert self.cutoff(_order(), shop=_shop()) == _local(2026, 9, 2, 18, 0)

    def test_preorder_without_slot_cuts_at_the_closing_of_that_day(self):
        order = _order(delivery_date="2026-09-04")  # sexta
        assert self.cutoff(order, shop=_shop()) == _local(2026, 9, 4, 18, 0)

    def test_canonical_slot_cuts_at_its_start(self):
        """Encomenda de turno: "A partir das 12h" começa às 12:00 — e a hora
        vem da configuração da casa, não do nome do slot."""
        order = _order(delivery_date="2026-09-04", delivery_time_slot="slot-12")
        assert self.cutoff(order, shop=_shop()) == _local(2026, 9, 4, 12, 0)

    def test_house_configured_slot_is_read_from_shop_defaults(self):
        shop = _shop(defaults={"pickup_slots": [{"ref": "slot-manha", "label": "Manhã", "starts_at": "07:30"}]})
        order = _order(delivery_date="2026-09-04", delivery_time_slot="slot-manha")
        assert self.cutoff(order, shop=shop) == _local(2026, 9, 4, 7, 30)

    def test_half_hour_window_of_today_cuts_at_its_start(self):
        """A janela de hoje se lê sozinha: "14:00-14:30" começa às 14:00."""
        order = _order(delivery_time_slot="14:00-14:30")
        assert self.cutoff(order, shop=_shop()) == _local(2026, 9, 2, 14, 0)

    def test_unreadable_slot_falls_back_to_the_closing(self):
        """"A combinar" ou um ref livre não é hora nenhuma: vale o fechamento."""
        order = _order(delivery_time_slot="manhã")
        assert self.cutoff(order, shop=_shop()) == _local(2026, 9, 2, 18, 0)

    def test_closed_day_without_slot_has_no_cutoff(self):
        """Domingo sem escala: não se inventa fechamento — vale só a janela."""
        order = _order(delivery_date="2026-09-06")
        assert self.cutoff(order, shop=_shop()) is None

    def test_shop_without_hours_has_no_cutoff(self):
        assert self.cutoff(_order(), shop=_shop(opening_hours={})) is None

    def test_without_a_shop_there_is_no_cutoff(self):
        cache.clear()
        assert self.cutoff(_order()) is None

    def test_the_cutoff_is_in_the_shop_timezone(self):
        """Um servidor em UTC não pode fechar a loja às 18h de Londres."""
        cutoff = self.cutoff(_order(), shop=_shop())
        assert cutoff is not None
        assert cutoff.utcoffset() == timedelta(hours=-3)

    def test_never_raises(self):
        """Um calendário quebrado não derruba a venda: na dúvida, só a janela."""
        with patch("shopman.shop.services.business_calendar.selling_hours_for", side_effect=RuntimeError("boom")):
            assert self.cutoff(_order(), shop=_shop()) is None


# ── 3. A janela é configuração de canal ───────────────────────────────────────


def _seed_pos_config() -> dict:
    """O ``_pos_config`` do seed, lido por AST — sem rodar o seed."""
    source = Path(django_settings.BASE_DIR) / "config" / "management" / "commands" / "seed.py"
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_pos_config" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("`_pos_config` não encontrado em config/management/commands/seed.py")


class TestChannelWindow:
    def test_default_is_two_hours(self):
        assert ChannelConfig().payment.link_timeout_minutes == 120

    def test_from_dict_reads_the_key(self):
        cfg = ChannelConfig.from_dict({"payment": {"method": "cash", "timing": "external", "link_timeout_minutes": 90}})
        assert cfg.payment.link_timeout_minutes == 90

    @pytest.mark.parametrize("minutes", [0, -30])
    def test_validate_rejects_a_window_that_is_not_positive(self, minutes):
        cfg = ChannelConfig.from_dict({"payment": {"method": "cash", "link_timeout_minutes": minutes}})
        with pytest.raises(ValueError, match="link_timeout_minutes"):
            cfg.validate()

    def test_the_seeded_pos_channel_declares_the_window(self):
        """``ChannelConfig`` descarta chave não declarada em silêncio — provar pela dataclass."""
        cfg = ChannelConfig.from_dict(_seed_pos_config())
        assert cfg.payment.link_timeout_minutes == 120
        cfg.validate()


class TestAdapterConfigCarriesWindowAndCutoff:
    """O adapter não conhece pedido nem calendário: os dois chegam prontos."""

    def setup_method(self):
        cache.clear()
        Channel.objects.create(
            ref="pdv",
            name="PDV",
            is_active=True,
            config={"payment": {"method": "cash", "timing": "external", "link_timeout_minutes": 90}},
        )

    def test_link_gets_window_and_cutoff(self):
        _shop()
        order = _order(payment={"method": "link"})
        cutoff = _local(2026, 9, 2, 11, 0)
        with patch.object(payment_deadline, "service_cutoff", return_value=cutoff):
            config = payment_service._adapter_config(order, method="link")

        assert config["link_timeout_minutes"] == 90
        assert config["link_expires_by"] == cutoff.isoformat()
        assert config["capture_method"] == "automatic"

    def test_without_cutoff_the_key_is_absent(self):
        _shop(opening_hours={})
        config = payment_service._adapter_config(_order(payment={"method": "link"}), method="link")
        assert config["link_timeout_minutes"] == 90
        assert "link_expires_by" not in config

    def test_pix_does_not_get_the_link_keys(self):
        _shop()
        config = payment_service._adapter_config(_order(payment={"method": "pix"}), method="pix")
        assert "link_timeout_minutes" not in config
        assert "link_expires_by" not in config


# ── 4. Stripe: o mesmo instante nos dois lados ────────────────────────────────


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
def test_stripe_link_sends_the_same_deadline_to_the_gateway_and_to_payman():
    """Sem mandar ``expires_at``, o Stripe usa 24 h por conta própria e a casa
    passa a ter dois relógios — a origem do problema. Um relógio, dois lados."""
    stripe = _stripe_double()
    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        intent = payment_stripe.create_intent(
            order_ref="PDV-LINK-STRIPE",
            amount_q=6300,
            method="link",
            metadata={"method": "link"},
            link_timeout_minutes=120,
        )

    assert intent.expires_at is not None
    assert timezone.is_aware(intent.expires_at)
    remaining = intent.expires_at - timezone.now()
    assert timedelta(minutes=110) < remaining <= timedelta(minutes=120)

    kwargs = stripe.checkout.Session.create.call_args.kwargs
    assert kwargs["expires_at"] == int(intent.expires_at.timestamp())

    db_intent = PaymanIntent.objects.get(ref=intent.intent_ref)
    assert db_intent.method == "link"
    assert db_intent.expires_at == intent.expires_at


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
def test_stripe_link_honours_the_service_cutoff():
    """Retirada daqui a 45 min: o link vence aí, não em duas horas."""
    stripe = _stripe_double()
    cutoff = timezone.now() + timedelta(minutes=45)
    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        intent = payment_stripe.create_intent(
            order_ref="PDV-LINK-CUTOFF",
            amount_q=6300,
            method="link",
            metadata={"method": "link"},
            link_timeout_minutes=120,
            link_expires_by=cutoff.isoformat(),
        )

    assert intent.expires_at == cutoff
    assert stripe.checkout.Session.create.call_args.kwargs["expires_at"] == int(cutoff.timestamp())


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
def test_stripe_link_without_config_still_expires_on_the_default_window():
    """``_adapter_config`` falhou ao resolver o canal: o link não nasce sem prazo."""
    stripe = _stripe_double()
    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        intent = payment_stripe.create_intent(
            order_ref="PDV-LINK-NOCFG",
            amount_q=6300,
            method="link",
            metadata={"method": "link"},
        )

    remaining = intent.expires_at - timezone.now()
    assert timedelta(minutes=110) < remaining <= _payment_link.default_link_timeout()


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
def test_stripe_card_keeps_no_deadline():
    """O cartão da loja online não ganha prazo: lá o cliente está na tela, e o
    abandono tem a própria rede (``reconcile_with_gateway_if_due``)."""
    stripe = _stripe_double("cs_test_card")
    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        intent = payment_stripe.create_intent(
            order_ref="WEB-CARD-1",
            amount_q=1000,
            method="card",
            metadata={"method": "card"},
        )

    assert intent.expires_at is None
    assert "expires_at" not in stripe.checkout.Session.create.call_args.kwargs
    assert PaymanIntent.objects.get(ref=intent.intent_ref).expires_at is None


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
def test_stripe_reused_link_intent_still_carries_its_deadline():
    """Retry com a mesma chave devolve o intent do banco — com o prazo dele,
    não sem prazo (senão o pedido perdia o ``expires_at`` no segundo ``initiate``)."""
    stripe = _stripe_double()
    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        first = payment_stripe.create_intent(
            order_ref="PDV-LINK-RETRY",
            amount_q=6300,
            method="link",
            metadata={"method": "link"},
            idempotency_key="link-retry-1",
            link_timeout_minutes=120,
        )
        second = payment_stripe.create_intent(
            order_ref="PDV-LINK-RETRY",
            amount_q=6300,
            method="link",
            metadata={"method": "link"},
            idempotency_key="link-retry-1",
            link_timeout_minutes=120,
        )

    stripe.checkout.Session.create.assert_called_once()
    assert second.intent_ref == first.intent_ref
    assert second.expires_at == first.expires_at


# ── Mock: o dev precisa ver o vencimento ──────────────────────────────────────


def test_mock_link_expires_on_the_same_clock():
    cutoff = timezone.now() + timedelta(minutes=50)
    intent = payment_mock.create_intent(
        order_ref="PDV-LINK-MOCK",
        amount_q=6300,
        method="link",
        metadata={"method": "link"},
        link_timeout_minutes=120,
        link_expires_by=cutoff.isoformat(),
    )

    assert intent.expires_at == cutoff
    assert PaymanIntent.objects.get(ref=intent.intent_ref).expires_at == intent.expires_at
    # E continua nascendo PENDENTE: prazo não é dinheiro.
    assert intent.status == "pending"


# ── 5. initiate: o prazo chega ao pedido e arma o timeout ────────────────────


def _pos_channel(**payment):
    cache.clear()
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={"payment": {"method": "cash", "timing": "external", **payment}},
    )


def _link_order(ref: str, **data) -> Order:
    return Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        status=Order.Status.ACCEPTED,
        total_q=6300,
        data={"origin_channel": "pos", "payment": {"method": "link", "collection": "terminal"}, **data},
    )


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_LINK_ADAPTERS)
def test_initiate_writes_the_deadline_on_the_order_and_arms_the_timeout():
    """``expires_at`` deixa de ser "PIX only" em ``order.data["payment"]``: é a
    chave que a tela do PDV e o aviso ao cliente leem para dizer "pague até …",
    e é o que agenda a Directive ``payment.timeout`` — a máquina inteira do
    vencimento já existia e estava parada por falta deste campo."""
    _pos_channel(link_timeout_minutes=120)
    _shop(opening_hours={})  # sem expediente conhecido: vale só a janela
    order = _link_order("PDV-LINK-INIT")

    payment_service.initiate(order)

    order.refresh_from_db()
    payment = order.data["payment"]
    assert payment["checkout_url"].startswith("http")
    expires_at = datetime.fromisoformat(payment["expires_at"])
    assert timezone.is_aware(expires_at)
    assert timedelta(minutes=110) < expires_at - timezone.now() <= timedelta(minutes=120)
    assert expires_at == PaymanIntent.objects.get(ref=payment["intent_ref"]).expires_at

    directive = Directive.objects.get(topic=PAYMENT_TIMEOUT, payload__order_ref=order.ref)
    assert directive.status == Directive.Status.QUEUED
    assert directive.available_at == expires_at
    assert directive.payload["intent_ref"] == payment["intent_ref"]
    assert directive.payload["expires_at"] == payment["expires_at"]


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_LINK_ADAPTERS)
def test_initiate_cuts_the_link_at_the_service_cutoff():
    """Ponta a ponta: a janela do canal (90 min) perde para a retirada em 40 min,
    e é ESSE instante que vai ao Payman, ao pedido e à Directive."""
    _pos_channel(link_timeout_minutes=90)
    _shop()
    order = _link_order("PDV-LINK-CUT")
    cutoff = (timezone.now() + timedelta(minutes=40)).replace(microsecond=0)

    with patch.object(payment_deadline, "service_cutoff", return_value=cutoff):
        payment_service.initiate(order)

    order.refresh_from_db()
    expires_at = datetime.fromisoformat(order.data["payment"]["expires_at"])
    assert expires_at == cutoff
    assert PaymanIntent.objects.get(order_ref=order.ref).expires_at == cutoff
    assert Directive.objects.get(topic=PAYMENT_TIMEOUT, payload__order_ref=order.ref).available_at == cutoff


# ── 6. O que o link vira no lifecycle ────────────────────────────────────────


def _pos_order(**payment):
    return SimpleNamespace(
        data={
            "origin_channel": "pos",
            "fulfillment_type": "pickup",
            "payment": {"collection": "terminal", "amount_q": 1000, **payment},
        }
    )


def test_a_link_sale_is_never_a_counter_handoff():
    """O cliente do link não está na loja: paga depois, do celular, e vem buscar.
    A sacola não está na mão dele — há trajeto pela frente por definição."""
    assert customer_holds_the_goods(_pos_order(method="cash")) is True
    assert customer_holds_the_goods(_pos_order(method="link")) is False
    assert customer_holds_the_goods(_pos_order(method="LINK")) is False
    assert lifecycle._counter_handoff(_pos_order(method="link")) is False


def test_kds_asks_the_same_question():
    """Uma resposta para os dois — senão uma regra entra no lifecycle e falta no KDS."""
    from shopman.shop.services.kds import _customer_holds_the_goods

    assert _customer_holds_the_goods(_pos_order(method="link")) is False
    assert _customer_holds_the_goods(_pos_order(method="cash")) is True


def test_link_requires_captured_payment_even_on_the_external_timing_channel():
    """``timing="external"`` descreve o balcão recebendo na hora (dinheiro,
    maquininha). O link existe justamente para o pedido que NÃO está no balcão:
    o dinheiro ainda não entrou, e a cozinha e a baixa de estoque esperam."""
    _pos_channel()
    config = ChannelConfig.for_channel("pdv")
    link_order = SimpleNamespace(ref="PDV-L", channel_ref="pdv", data=_pos_order(method="link").data)
    cash_order = SimpleNamespace(ref="PDV-C", channel_ref="pdv", data=_pos_order(method="cash").data)

    assert lifecycle._requires_payment_before_physical_work(link_order, config) is True
    assert lifecycle._requires_payment_before_physical_work(cash_order, config) is False
    assert lifecycle._stock_fulfill_allowed(cash_order, config) is True
    with patch.object(payment_service, "has_sufficient_captured_payment", return_value=False):
        assert lifecycle._stock_fulfill_allowed(link_order, config) is False
