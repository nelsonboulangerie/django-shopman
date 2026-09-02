"""O link de pagamento do pedido remoto sai da casa sozinho (Frente 2 do WP-PAGAMENTO).

Antes, o operador copiava a URL e mandava à mão — e quem manda à mão esquece,
sobretudo no pico, que é quando o pedido remoto entra. E mesmo que o código
mandasse, o canal `pdv` herdava o `console` da loja, que sempre "dá certo" e
curto-circuita a cadeia: nenhum aviso de PDV alcançava o cliente.

Cinco coisas, cada uma com o seu teste:

1. o prazo em copy de cliente ("hoje às 18h", "amanhã às 9h") — e a frase
   inteira SOME quando não há prazo, em vez de sair "O link vale até .";
2. o contexto exporta `checkout_url` (a cobrança), distinto do `payment_url`
   (o acompanhamento);
3. o canal `pdv` semeado avisa por WhatsApp → e-mail → SMS, e pula o backend
   sem destinatário;
4. a venda em link enfileira UMA Directive `payment_link_sent`, nunca quando o
   gateway falhou ou a forma é outra;
5. o ManyChat recebe os campos personalizados que o template aprovado lê.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.orderman.models import Directive, Order

from shopman.shop.adapters import notification_email, notification_manychat, notification_sms
from shopman.shop.adapters._notification_templates import derive_context, render_message, render_template
from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel, Shop
from shopman.shop.services import notification as notification_svc
from shopman.shop.services import pos as pos_service
from shopman.shop.services.business_calendar import format_deadline
from shopman.shop.services.notification import _build_context

CHECKOUT_URL = "https://checkout.stripe.com/c/pay/cs_test_a1b2c3"


def _local(*args) -> datetime:
    return timezone.make_aware(datetime(*args))


def _seed_source() -> ast.Module:
    source = Path(settings.BASE_DIR) / "config" / "management" / "commands" / "seed.py"
    return ast.parse(source.read_text(encoding="utf-8"))


def _seed_assignment(name: str):
    """Um dicionário literal do seed, lido por AST — sem rodar o seed."""
    for node in ast.walk(_seed_source()):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"`{name}` não encontrado em config/management/commands/seed.py")


def _order(*, phone: str | None = "+5543999990001", email: str | None = None, expires_at: str | None = None):
    """Pedido do PDV: cliente por telefone e/ou e-mail, SEM `customer.uuid`, com link."""
    customer: dict = {"name": "Joyce", "ref": "CLI-1"}
    if phone:
        customer["phone"] = phone
    if email:
        customer["email"] = email
    payment = {"method": "link", "intent_ref": "PI-1", "amount_q": 3800, "checkout_url": CHECKOUT_URL}
    if expires_at:
        payment["expires_at"] = expires_at
    order = MagicMock()
    order.ref = "PDV-1"
    order.total_q = 3800
    order.status = "accepted"
    order.channel_ref = "pdv"
    order.handle_type = "phone"
    order.handle_ref = phone or ""
    order.data = {"customer": customer, "fulfillment_type": "pickup", "payment": payment}
    order.snapshot = {"items": []}
    return order


# ══════════════════════════════════════════════════════════════════════
# 1. O prazo em copy de cliente
# ══════════════════════════════════════════════════════════════════════


class TestFormatDeadline:
    NOW = _local(2026, 9, 2, 10, 0)  # quarta-feira

    def test_hoje(self):
        assert format_deadline(_local(2026, 9, 2, 18, 0), now=self.NOW) == "hoje às 18h"

    def test_amanha_com_minutos(self):
        assert format_deadline(_local(2026, 9, 3, 9, 30), now=self.NOW) == "amanhã às 9h30"

    def test_depois_de_amanha_leva_a_data(self):
        """"sábado às 14h" sem o dia deixa dúvida de QUAL sábado num link de dias."""
        assert format_deadline(_local(2026, 9, 5, 14, 0), now=self.NOW) == "sáb. 5/9 às 14h"

    def test_prazo_vencido_cala(self):
        """Dizer "vale até hoje às 9h" às 10h é promessa errada."""
        assert format_deadline(_local(2026, 9, 2, 9, 0), now=self.NOW) == ""

    def test_sem_prazo_cala(self):
        assert format_deadline(None, now=self.NOW) == ""

    def test_utc_vira_hora_local(self):
        """O gateway grava em UTC; o cliente lê no fuso da casa."""
        value = datetime(2026, 9, 2, 21, 0, tzinfo=UTC)  # 18h em São Paulo
        assert format_deadline(value, now=self.NOW) == "hoje às 18h"


class TestDeriveContextPrazo:
    def test_com_prazo_gravado_as_duas_chaves_existem(self):
        expires_at = (timezone.now() + timedelta(hours=2)).isoformat()
        ctx = derive_context({"payment": {"method": "link", "expires_at": expires_at}})

        assert ctx["payment_deadline"], "o prazo cru é o campo personalizado do ManyChat"
        assert ctx["payment_deadline_note"] == f"\nO link vale até {ctx['payment_deadline']}."

    def test_sem_prazo_as_duas_chaves_sao_vazias(self):
        ctx = derive_context({"payment": {"method": "link", "checkout_url": CHECKOUT_URL}})
        assert ctx["payment_deadline"] == ""
        assert ctx["payment_deadline_note"] == ""

    def test_sem_pagamento_nenhum_as_chaves_existem_vazias(self):
        """Chamada direta ao adapter (campanha, compras) não pode deixar rótulo cru."""
        ctx = derive_context({})
        assert ctx["payment_deadline"] == ""
        assert ctx["payment_deadline_note"] == ""

    def test_prazo_ilegivel_cala_em_vez_de_quebrar(self):
        ctx = derive_context({"payment": {"expires_at": "amanhã de manhã"}})
        assert ctx["payment_deadline"] == ""
        assert ctx["payment_deadline_note"] == ""

    def test_idempotente(self):
        expires_at = (timezone.now() + timedelta(hours=2)).isoformat()
        once = derive_context({"payment": {"expires_at": expires_at}})
        assert derive_context(once) == once


# ══════════════════════════════════════════════════════════════════════
# 2. O contexto do pedido exporta a URL da cobrança
# ══════════════════════════════════════════════════════════════════════


@override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://loja.test")
def test_build_context_exporta_checkout_url_distinto_do_payment_url():
    context = _build_context(_order(), {"order_ref": "PDV-1"}, "payment_link_sent")

    assert context["checkout_url"] == CHECKOUT_URL
    assert context["payment_url"] == "https://loja.test/pedido/PDV-1", "o acompanhamento segue sendo outro link"


@override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://loja.test")
def test_build_context_sem_pagamento_exporta_checkout_url_vazio():
    order = _order()
    order.data.pop("payment")
    context = _build_context(order, {"order_ref": "PDV-1"}, "order_accepted")
    assert context["checkout_url"] == ""


# ══════════════════════════════════════════════════════════════════════
# 3. Nenhum canal manda rótulo pendurado
# ══════════════════════════════════════════════════════════════════════


def _renders(context: dict) -> dict[str, str]:
    ctx = derive_context(context)
    return {
        "whatsapp": notification_manychat._build_message("payment_link_sent", ctx),
        "sms": notification_sms._build_message("payment_link_sent", ctx),
        "email.body": render_message("payment_link_sent", ctx, notification_email.BODY_TEMPLATES),
        "email.subject": render_template(notification_email.SUBJECT_TEMPLATES["payment_link_sent"], ctx),
        "seed": render_template(_seed_assignment("FALLBACK_TEMPLATES")["payment_link_sent"]["body"], ctx),
    }


@pytest.mark.django_db
class TestRenderDosTresCanais:
    @pytest.fixture
    def with_deadline(self):
        expires_at = (timezone.now() + timedelta(hours=3)).isoformat()
        return _build_context(_order(expires_at=expires_at), {"order_ref": "PDV-1"}, "payment_link_sent")

    @pytest.fixture
    def without_deadline(self):
        return _build_context(_order(), {"order_ref": "PDV-1"}, "payment_link_sent")

    def test_com_prazo_todo_canal_diz_ate_quando(self, with_deadline):
        for channel, text in _renders(with_deadline).items():
            if channel == "email.subject":
                continue
            assert "O link vale até " in text, f"{channel}: {text!r}"
            assert "vale até ." not in text, f"{channel}: {text!r}"
            assert CHECKOUT_URL in text, f"{channel}: {text!r}"
            assert "{" not in text, f"placeholder cru em {channel}: {text!r}"

    def test_sem_prazo_nenhum_canal_deixa_rotulo_pendurado(self, without_deadline):
        """"O link vale até ." é proibido — a frase inteira some."""
        for channel, text in _renders(without_deadline).items():
            assert "vale até" not in text, f"{channel}: {text!r}"
            assert "{" not in text, f"placeholder cru em {channel}: {text!r}"
            if channel != "email.subject":
                assert CHECKOUT_URL in text, f"{channel}: {text!r}"

    def test_o_cliente_e_chamado_pelo_nome_e_ve_o_total(self, without_deadline):
        """⚠️ O total era `:,.2f` cru — "R$ 38.00" com ponto americano — na mensagem
        que o cliente recebe. O SMS de fallback não cumprimenta: é curto de propósito."""
        for channel, text in _renders(without_deadline).items():
            if channel == "email.subject":
                continue
            if channel != "sms":
                assert "Joyce" in text, f"{channel}: {text!r}"
            assert "R$ 38,00" in text, f"{channel}: {text!r}"
            assert "38.00" not in text, f"ponto decimal americano em {channel}: {text!r}"

    def test_o_sms_nao_leva_o_negrito_do_template_do_admin(self, without_deadline):
        from shopman.shop.models import NotificationTemplate

        seeded = _seed_assignment("FALLBACK_TEMPLATES")["payment_link_sent"]
        NotificationTemplate.objects.create(event="payment_link_sent", is_active=True, **seeded)

        sms = notification_sms._build_message("payment_link_sent", without_deadline)
        assert "*" not in sms
        assert "PDV-1" in sms and CHECKOUT_URL in sms


class TestSeedDoTemplate:
    def test_o_evento_tem_linha_no_seed(self):
        templates = _seed_assignment("FALLBACK_TEMPLATES")
        assert "payment_link_sent" in templates, "sem linha, o lojista não edita nem cola o flow do ManyChat"
        body = templates["payment_link_sent"]["body"]
        assert "{checkout_url}" in body, "o aviso manda para a COBRANÇA, não para o acompanhamento"
        assert "{payment_url}" not in body
        assert "{payment_deadline_note}" in body, "só a chave auto-suprimível pode carregar o prazo"
        assert "{payment_deadline}" not in body.replace("{payment_deadline_note}", "")

    def test_o_evento_e_ativo_no_service(self):
        """Falha de entrega tem que gritar, não sumir: é a cobrança inteira."""
        assert "payment_link_sent" in notification_svc._ACTIVE_NOTIFICATION_TEMPLATES


# ══════════════════════════════════════════════════════════════════════
# 4. A cadeia do canal `pdv`
# ══════════════════════════════════════════════════════════════════════


def _seeded_pos_channel() -> Channel:
    cache.clear()
    return Channel.objects.create(ref="pdv", name="PDV", is_active=True, config=_seed_assignment("_pos_config"))


class TestCadeiaDoPdv:
    def test_a_config_semeada_declara_whatsapp_email_sms(self):
        """`ChannelConfig` descarta chave não declarada em silêncio — provar pela dataclass."""
        notifications = ChannelConfig.from_dict(_seed_assignment("_pos_config")).notifications
        assert notifications.backend == "manychat"
        assert notifications.fallback_chain == ["email", "sms"]

    @pytest.mark.django_db
    def test_a_cadeia_resolvida_do_canal_nao_passa_pelo_console(self):
        Shop.objects.create(name="Test Shop", brand_name="Test")
        _seeded_pos_channel()

        chain = notification_svc._resolve_backend_chain(_order())

        assert chain == ["manychat", "email", "sms"]
        assert "console" not in chain, "o console sempre 'dá certo' e engole a cadeia"


def _deliver(order, *, outcomes: dict[str, bool]):
    """Roda a cadeia semeada com os backends de pé e devolve quem foi tentado."""
    backend = SimpleNamespace(is_available=lambda: True)

    def _notify(*, event, recipient, context, backend):
        return SimpleNamespace(success=outcomes.get(backend, True), error=None if outcomes.get(backend, True) else "down")

    with patch("shopman.shop.notifications.get_backend", return_value=backend):
        with patch.object(notification_svc, "notify", side_effect=_notify) as mock_notify:
            success, error = notification_svc.deliver_order_notification(
                order, "payment_link_sent", {"order_ref": order.ref}
            )
    used = [call.kwargs["backend"] for call in mock_notify.call_args_list]
    return success, error, used


@pytest.mark.django_db
class TestACadeiaPulaQuemNaoTemDestinatario:
    @pytest.fixture(autouse=True)
    def _pdv(self, settings):
        settings.DEBUG = False
        Shop.objects.create(name="Test Shop", brand_name="Test")
        _seeded_pos_channel()

    def test_cliente_com_telefone_recebe_pelo_whatsapp(self):
        success, _, used = _deliver(_order(), outcomes={})
        assert success is True
        assert used == ["manychat"]

    def test_cliente_so_com_email_cai_direto_no_email(self):
        """WhatsApp e SMS não têm para quem mandar: o mecanismo pula, sem falhar."""
        success, _, used = _deliver(_order(phone=None, email="joyce@casa.com"), outcomes={})
        assert success is True
        assert used == ["email"]

    def test_whatsapp_fora_do_ar_cai_no_sms_quando_nao_ha_email(self):
        success, _, used = _deliver(_order(), outcomes={"manychat": False})
        assert success is True
        assert used == ["manychat", "sms"]

    def test_sem_contato_nenhum_o_aviso_ativo_grita(self):
        success, error, used = _deliver(_order(phone=None), outcomes={})
        assert used == []
        assert success is False
        assert error == "no active notification recipient available"


# ══════════════════════════════════════════════════════════════════════
# 5. O gatilho na venda do PDV
# ══════════════════════════════════════════════════════════════════════

_LINK_ADAPTERS = override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "link": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    }
)


class _Counter:
    """Um balcão com o canal `pdv` semeado, um item e um operador com turno aberto."""

    def __init__(self):
        from shopman.offerman.models import Product

        Shop.objects.create(name="Test Shop", brand_name="Test")
        _seeded_pos_channel()
        Product.objects.create(sku="PAO", name="Pão", base_price_q=1200, is_published=True, is_sellable=True)
        self.operator = get_user_model().objects.create_user(username="marina", password="x")
        self.shift = cash.open_shift(operator=self.operator, float_q=10000)

    def close(self, *, client_request_id: str, **overrides):
        payload = {
            "items": [{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200}],
            "customer_name": "Joyce",
            "customer_phone": "43999990000",
            "payment_tenders": [{"method": "link", "amount_q": 1200, "collection": "terminal"}],
            "client_request_id": client_request_id,
            "cash_shift_id": self.shift.pk,
        }
        payload.update(overrides)
        return pos_service.close_sale(
            channel_ref="pdv",
            payload=payload,
            actor=f"pos:{self.operator.username}",
            operator_username=self.operator.username,
        )


@pytest.fixture
def counter(db):
    return _Counter()


def _link_directives(order_ref: str):
    return Directive.objects.filter(
        topic=notification_svc.TOPIC, payload__template="payment_link_sent", payload__order_ref=order_ref
    )


@_LINK_ADAPTERS
def test_a_venda_em_link_enfileira_um_aviso_so(counter):
    result = counter.close(client_request_id="link-1")

    assert result.payment.get("checkout_url", "").startswith("http")
    (directive,) = _link_directives(result.order_ref)
    assert directive.status == "queued"
    assert directive.payload["requires_active_notification"] is True, "falha de entrega tem que gritar"


@_LINK_ADAPTERS
def test_o_retry_do_pdv_nao_manda_o_link_duas_vezes(counter):
    result = counter.close(client_request_id="link-2")
    order = Order.objects.get(ref=result.order_ref)

    notification_svc.send(order, "payment_link_sent")

    assert _link_directives(result.order_ref).count() == 1


@_LINK_ADAPTERS
def test_gateway_que_falhou_nao_manda_link_nenhum(counter):
    """Sem `checkout_url` não há o que mandar — e mandar seria prometer cobrança que não existe."""
    with patch.object(pos_service.payment_service, "initiate", side_effect=RuntimeError("gateway down")):
        result = counter.close(client_request_id="link-3")

    assert result.payment.get("status") == "error"
    assert not _link_directives(result.order_ref).exists()


@_LINK_ADAPTERS
def test_outra_forma_de_pagamento_nao_manda_link(counter):
    result = counter.close(
        client_request_id="pix-1",
        payment_tenders=[{"method": "pix", "amount_q": 1200, "collection": "terminal"}],
    )
    assert not _link_directives(result.order_ref).exists()


@_LINK_ADAPTERS
def test_falha_ao_enfileirar_nao_derruba_a_venda(counter):
    """A cobrança já existe e a tela mostra a URL: o operador ainda manda à mão."""
    with patch.object(notification_svc, "send", side_effect=RuntimeError("fila fora do ar")):
        result = counter.close(client_request_id="link-4")

    assert result.payment.get("checkout_url", "").startswith("http")


# ══════════════════════════════════════════════════════════════════════
# 6. O ManyChat recebe os campos que o template aprovado lê
# ══════════════════════════════════════════════════════════════════════

#: Os nomes EXATOS que o Pablo cria no painel do ManyChat.
MANYCHAT_FIELDS = {"order_ref", "customer_name_greeting", "total", "checkout_url", "payment_deadline"}


@pytest.fixture
def manychat_calls(monkeypatch, db):
    from shopman.shop.models import NotificationTemplate

    NotificationTemplate.objects.create(
        event="payment_link_sent", subject="x", body="y", whatsapp_flow_ns="content20260902120000_1",
    )
    seen: list[tuple[str, dict]] = []

    def _fake(endpoint, payload, config):
        seen.append((endpoint, payload))
        return {"success": True}

    monkeypatch.setattr(notification_manychat, "_api_call", _fake)
    monkeypatch.setattr(notification_manychat, "_get_config", lambda: {"api_token": "tok", "flow_map": {}})
    monkeypatch.setattr(notification_manychat, "_resolve_subscriber", lambda *a, **k: "sub-1")
    return seen


def _fields(calls) -> dict[str, str]:
    return {
        payload["field_name"]: payload["field_value"]
        for endpoint, payload in calls
        if endpoint.endswith("setCustomFieldByName")
    }


@override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://loja.test")
def test_os_cinco_campos_chegam_ao_manychat(manychat_calls):
    expires_at = (timezone.now() + timedelta(hours=3)).isoformat()
    context = _build_context(_order(expires_at=expires_at), {"order_ref": "PDV-1"}, "payment_link_sent")

    assert notification_manychat.send("+5543999990001", "payment_link_sent", context) is True

    fields = _fields(manychat_calls)
    assert MANYCHAT_FIELDS <= set(fields), MANYCHAT_FIELDS - set(fields)
    assert fields["order_ref"] == "PDV-1"
    assert fields["customer_name_greeting"] == ", Joyce"
    assert fields["total"] == "R$ 38,00"
    assert fields["checkout_url"] == CHECKOUT_URL
    assert fields["payment_deadline"].startswith(("hoje às", "amanhã às"))
    assert "phone" not in fields, "no ManyChat o `phone` é NULO; nunca sai daqui"
    assert manychat_calls[-1][0].endswith("sendFlow")


@override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://loja.test")
def test_sem_prazo_o_campo_nao_e_gravado(manychat_calls):
    """Campo vazio não sobrescreve: o template do painel decide o que mostrar sem prazo."""
    context = _build_context(_order(), {"order_ref": "PDV-1"}, "payment_link_sent")

    notification_manychat.send("+5543999990001", "payment_link_sent", context)

    fields = _fields(manychat_calls)
    assert "payment_deadline" not in fields
    assert fields["checkout_url"] == CHECKOUT_URL
