"""Estorno no Admin de cobranças: dinheiro de verdade, pelo gateway, com dupla confirmação.

As duas ações (`refund` = total, `refund-amount` = um valor) são dialog actions
oficiais do Unfold. Quem estorna é quem tem `payman.refund_paymentintent`; ver a
cobrança (`view_paymentintent`) não basta. E o estorno só acontece com a
confirmação marcada: escolher a ação é o primeiro gesto, confirmar é o segundo.

Desde 20/10/2026 (decisão do dono) o estorno devolve o dinheiro pelo gateway da
cobrança (Pix Efí, cartão Stripe), pelo mesmo caminho do estorno do pedido
(`PAYMAN["REFUND_BACKEND"]` → `services.payment.refund_intent_at_gateway` →
adapters). Os gateways aqui são dublês: a Stripe por `_get_stripe`, a Efí por
`_request`.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.test import override_settings
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.payman.service import PaymentService

from shopman.shop.models import Shop

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("gateway_adapters"),
]


@pytest.fixture
def gateway_adapters():
    with override_settings(
        SHOPMAN_PAYMENT_ADAPTERS={
            "pix": "shopman.shop.adapters.payment_efi",
            "card": "shopman.shop.adapters.payment_stripe",
        },
        SHOPMAN_EFI={"sandbox": True},
        PAYMAN={"REFUND_BACKEND": "shopman.shop.adapters.payman_refund.GatewayRefundBackend"},
    ):
        yield


# ── dublês dos gateways ─────────────────────────────────────────────


class FakeStripe:
    """`stripe.Refund.create` idempotente por chave, como a Stripe de verdade."""

    def __init__(self, *, error: str | None = None):
        self.error = error
        self.calls: list[dict] = []
        self._by_key: dict[str, SimpleNamespace] = {}
        self.Refund = SimpleNamespace(create=self._create)

    def _create(self, **params):
        self.calls.append(params)
        if self.error:
            raise RuntimeError(self.error)
        key = params.get("idempotency_key")
        if key in self._by_key:
            return self._by_key[key]
        refund = SimpleNamespace(id=f"re_{len(self._by_key) + 1}", amount=params["amount"])
        self._by_key[key] = refund
        return refund

    @property
    def refunds_created(self) -> int:
        return len(self._by_key)


@pytest.fixture
def stripe():
    fake = FakeStripe()
    with patch("shopman.shop.adapters.payment_stripe._get_stripe", return_value=fake):
        yield fake


class FakeEfi:
    """`/v2/pix/{e2e}/devolucao/{dev_id}` idempotente por `dev_id`, como a Efí."""

    def __init__(self, *, put_error: Exception | None = None):
        self.put_error = put_error
        self.puts: list[tuple[str, dict]] = []

    def __call__(self, method, path, payload=None):
        if method == "GET":
            return {"status": "CONCLUIDA", "pix": [{"endToEndId": "E2E-ADMIN"}], "valor": {"original": "100.00"}}
        self.puts.append((path, payload))
        if self.put_error is not None:
            raise self.put_error
        return {"id": path.rsplit("/", 1)[-1], "valor": payload["valor"]}

    @property
    def distinct_refunds(self) -> int:
        return len({path for path, _payload in self.puts})


# ── cobranças ───────────────────────────────────────────────────────


def _captured(method: str, gateway: str, amount_q: int, gateway_data: dict | None = None):
    n = PaymentIntent.objects.count()
    intent = PaymentService.create_intent(
        f"ORD-ADMINREF{n}", amount_q, method, gateway=gateway, gateway_id=f"gw-{n}", gateway_data=gateway_data
    )
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
    return PaymentService.get(intent.ref)


def _card(amount_q=10000):
    return _captured("card", "stripe", amount_q)


def _pix(amount_q=10000):
    return _captured("pix", "efi", amount_q, {"provider_environment": "sandbox"})


def _total_url(pk):
    return f"/admin/payman/paymentintent/{pk}/refund/"


def _amount_url(pk):
    return f"/admin/payman/paymentintent/{pk}/refund-amount/"


def _key(client, url) -> str:
    """A chave que o diálogo aberto carrega (uma por GET)."""
    body = client.get(url).content.decode()
    match = re.search(r'name="refund_key" value="([0-9a-f]{32})"', body)
    assert match, "o diálogo não trouxe a chave de idempotência"
    return match.group(1)


def _post(client, url, **fields):
    data = {"_form_submitted": "true", "confirm": "on", "refund_key": _key(client, url)}
    data.update(fields)
    return client.post(url, data)


def _messages(resp) -> list[str]:
    return [str(m) for m in resp.wsgi_request._messages]


def _staff(username: str, *perms: str) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    for perm in perms:
        app_label, codename = perm.split(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return User.objects.get(pk=user.pk)


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def refunder_client(client, shop):
    client.force_login(
        _staff("dono-estorno", "payman.view_paymentintent", "payman.refund_paymentintent")
    )
    return client


# ── quem estorna ────────────────────────────────────────────────────


@pytest.mark.parametrize("url", [_total_url, _amount_url])
def test_view_only_staff_cannot_refund(client, shop, stripe, url):
    intent = _card(10000)
    client.force_login(_staff("so-ve", "payman.view_paymentintent"))

    resp = client.post(url(intent.pk), {"_form_submitted": "true", "confirm": "on", "refund_key": "a" * 32})

    assert resp.status_code == 403
    assert PaymentService.refunded_total(intent.ref) == 0
    assert stripe.calls == []


def test_permission_exists_on_the_model():
    assert Permission.objects.filter(
        content_type__app_label="payman", codename="refund_paymentintent"
    ).exists()


def test_refund_permission_goes_to_dono_not_gerente():
    """Estorno é dinheiro: mesma régua do `audit_shift`, do Dono e nunca do Gerente."""
    call_command("setup_groups")
    holders = set(
        Group.objects.filter(
            permissions__content_type__app_label="payman",
            permissions__codename="refund_paymentintent",
        ).values_list("name", flat=True)
    )
    assert holders == {"Dono"}


# ── segunda confirmação ─────────────────────────────────────────────


def test_amount_dialog_renders_with_available_and_confirmation(refunder_client):
    intent = _card(10000)
    resp = refunder_client.get(_amount_url(intent.pk))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'id="dialog"' in body
    assert "100,00" in body  # disponível no texto de ajuda
    assert 'name="confirm"' in body
    assert 'name="refund_key"' in body


def test_dialog_tells_the_truth_about_the_money(refunder_client):
    """A copy diz que o dinheiro volta ao cliente, e em quanto tempo; sem travessão."""
    intent = _card(10000)
    for url in (_total_url, _amount_url):
        body = refunder_client.get(url(intent.pk)).content.decode()
        assert "Daqui o dinheiro não sai" not in body
        assert "pelo mesmo meio do pagamento" in body
        assert "No Pix o dinheiro volta em instantes" in body
        assert "conforme o banco do cartão" in body
        assert "—" not in body.split('id="dialog"', 1)[1].split("</form>", 1)[0]


@pytest.mark.parametrize("url", [_total_url, _amount_url])
def test_without_the_confirmation_nothing_is_refunded(refunder_client, stripe, url):
    intent = _card(10000)
    resp = refunder_client.post(
        url(intent.pk),
        {"_form_submitted": "true", "amount_reais": "30.00", "refund_key": _key(refunder_client, url(intent.pk))},
    )
    assert resp.status_code == 200  # diálogo volta com o erro
    assert "Marque a confirmação para estornar." in resp.content.decode()
    assert PaymentService.refunded_total(intent.ref) == 0
    assert stripe.calls == []


def test_refund_above_available_is_rejected(refunder_client, stripe):
    intent = _card(4000)
    resp = _post(refunder_client, _amount_url(intent.pk), amount_reais="99.00")
    assert resp.status_code == 200  # diálogo volta com o erro
    assert "Valor acima do disponível" in resp.content.decode()
    assert PaymentService.refunded_total(intent.ref) == 0
    assert stripe.calls == []


# ── cartão (Stripe) ─────────────────────────────────────────────────


def test_card_total_refund_goes_through_stripe(refunder_client, stripe):
    intent = _card(7000)
    resp = _post(refunder_client, _total_url(intent.pk))

    assert resp.status_code == 302
    assert len(stripe.calls) == 1
    call = stripe.calls[0]
    assert call["payment_intent"] == intent.gateway_id
    assert call["amount"] == 7000
    assert call["idempotency_key"].startswith(f"admin-refund:{intent.ref}:")
    assert PaymentService.refunded_total(intent.ref) == 7000
    txn = PaymentTransaction.objects.get(intent=intent, type="refund")
    assert txn.gateway_id == "re_1"
    assert any("devolvidos ao cliente" in m for m in _messages(resp))


def test_card_partial_refund_and_blank_takes_the_rest(refunder_client, stripe):
    intent = _card(10000)
    _post(refunder_client, _amount_url(intent.pk), amount_reais="30.00")
    assert PaymentService.refunded_total(intent.ref) == 3000

    _post(refunder_client, _amount_url(intent.pk), amount_reais="")
    assert PaymentService.refunded_total(intent.ref) == 10000
    assert [c["amount"] for c in stripe.calls] == [3000, 7000]


def test_double_click_refunds_once(refunder_client, stripe):
    """O duplo clique reenvia a mesma chave: a Stripe devolve a mesma devolução, o livro grava uma."""
    intent = _card(10000)
    url = _amount_url(intent.pk)
    data = {"_form_submitted": "true", "confirm": "on", "amount_reais": "30.00", "refund_key": _key(refunder_client, url)}

    first = refunder_client.post(url, data)
    second = refunder_client.post(url, data)

    assert first.status_code == second.status_code == 302
    assert len(stripe.calls) == 2
    assert stripe.refunds_created == 1
    assert PaymentService.refunded_total(intent.ref) == 3000
    assert PaymentTransaction.objects.filter(intent=intent, type="refund").count() == 1


def test_double_click_on_total_refunds_once(refunder_client, stripe):
    intent = _card(5000)
    url = _total_url(intent.pk)
    data = {"_form_submitted": "true", "confirm": "on", "refund_key": _key(refunder_client, url)}

    refunder_client.post(url, data)
    second = refunder_client.post(url, data)

    assert stripe.refunds_created == 1
    assert PaymentService.refunded_total(intent.ref) == 5000
    assert any("não tem valor disponível" in m for m in _messages(second))


def test_stripe_failure_records_nothing_and_says_why(refunder_client):
    fake = FakeStripe(error="Charge ch_1 has already been refunded.")
    intent = _card(5000)
    with patch("shopman.shop.adapters.payment_stripe._get_stripe", return_value=fake):
        resp = _post(refunder_client, _total_url(intent.pk))

    assert resp.status_code == 302
    assert PaymentService.refunded_total(intent.ref) == 0
    errors = _messages(resp)
    assert any(
        "O estorno foi recusado (Stripe), e nada foi registrado aqui." in m and "already been refunded" in m
        for m in errors
    ), errors
    assert not LogEntry.objects.exists()


def test_audit_trail_names_who_refunded(refunder_client, stripe):
    intent = _card(5000)
    _post(refunder_client, _total_url(intent.pk))

    txn = PaymentTransaction.objects.get(intent=intent, type="refund")
    assert txn.reason == "Estorno no Admin por dono-estorno"
    entry = LogEntry.objects.get(object_id=str(intent.pk))
    assert entry.user.username == "dono-estorno"
    assert "R$ 50,00" in entry.change_message


# ── Pix (Efí) ───────────────────────────────────────────────────────


def test_pix_partial_refund_goes_through_efi(refunder_client):
    efi = FakeEfi()
    intent = _pix(10000)
    with patch("shopman.shop.adapters.payment_efi._request", side_effect=efi):
        resp = _post(refunder_client, _amount_url(intent.pk), amount_reais="25.50")

    assert resp.status_code == 302
    assert len(efi.puts) == 1
    path, payload = efi.puts[0]
    assert path.startswith("/v2/pix/E2E-ADMIN/devolucao/")
    assert payload == {"valor": "25.50"}
    assert PaymentService.refunded_total(intent.ref) == 2550


def test_pix_double_click_presents_the_same_devolucao(refunder_client):
    efi = FakeEfi()
    intent = _pix(10000)
    url = _amount_url(intent.pk)
    data = {"_form_submitted": "true", "confirm": "on", "amount_reais": "10.00", "refund_key": _key(refunder_client, url)}
    with patch("shopman.shop.adapters.payment_efi._request", side_effect=efi):
        refunder_client.post(url, data)
        refunder_client.post(url, data)

    assert len(efi.puts) == 2
    assert efi.distinct_refunds == 1
    assert PaymentService.refunded_total(intent.ref) == 1000


def test_pix_timeout_records_nothing_and_warns_loud(refunder_client):
    efi = FakeEfi(put_error=TimeoutError("read timed out"))
    intent = _pix(10000)
    with patch("shopman.shop.adapters.payment_efi._request", side_effect=efi):
        resp = _post(refunder_client, _total_url(intent.pk))

    assert PaymentService.refunded_total(intent.ref) == 0
    errors = _messages(resp)
    assert any("o estorno pode ter saído" in m and "Confira no painel" in m for m in errors), errors

    from shopman.backstage.models import OperatorAlert

    assert OperatorAlert.objects.filter(type="payment_refund_failed").exists()


# ── cobrança sem gateway: o Admin não finge que devolveu ───────────


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("cash", "a devolução sai da gaveta"),
        ("credit", "o estorno se faz na própria maquininha"),
        ("external", "o estorno se faz na própria maquininha"),
    ],
)
def test_without_gateway_refuses_and_points_where(refunder_client, method, expected):
    intent = PaymentService.settle(f"ORD-SEMGW-{method}", 4000, method)
    resp = _post(refunder_client, _total_url(intent.pk))

    assert PaymentService.refunded_total(intent.ref) == 0
    assert any(expected in m for m in _messages(resp))


def test_without_backend_configured_nothing_is_refunded(refunder_client, stripe):
    intent = _card(5000)
    with override_settings(PAYMAN={}):
        resp = _post(refunder_client, _total_url(intent.pk))

    assert PaymentService.refunded_total(intent.ref) == 0
    assert stripe.calls == []
    assert any("não está configurado" in m for m in _messages(resp))


# ── contrato do Admin ───────────────────────────────────────────────


def test_admin_system_check_does_not_touch_the_database(django_assert_num_queries):
    """A forma pontuada faria o check do Unfold (admin.E129) consultar `Permission`.

    O contrato de produção roda `check --deploy` sem banco: a consulta derrubava ele.
    """
    from django.contrib import admin as django_admin

    model_admin = django_admin.site._registry[PaymentIntent]
    with django_assert_num_queries(0):
        assert model_admin.check() == []


def test_bulk_refund_action_no_longer_exists():
    """Ação de lote do Django roda sem diálogo: estorno é um por vez."""
    from django.contrib import admin as django_admin

    model_admin = django_admin.site._registry[PaymentIntent]
    assert "refund_selected" not in (model_admin.actions or [])
