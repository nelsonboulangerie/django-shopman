"""O freio e o medidor da porta de IA (ID3A-PLAN, E1; decisão D-039)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from shopman.shop import ai, ai_governor
from shopman.shop.models import AiInvocation, AiOutcome, AiSpendDay, Shop
from shopman.shop.tests.ai_support import configure_ai, configure_jev

pytestmark = pytest.mark.django_db


class FakeMessages:
    def __init__(self, usage=None, error: Exception | None = None):
        self.usage = usage or {"input_tokens": 1000, "output_tokens": 100}
        self.error = error
        self.calls: list[dict] = []

    def create(self, **request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return SimpleNamespace(usage=SimpleNamespace(**self.usage), content=[])


def _client(messages: FakeMessages, purpose: str = "copy"):
    fake_sdk = SimpleNamespace(messages=messages)
    with mock.patch("anthropic.Anthropic", return_value=fake_sdk):
        client, model = ai.anthropic_client(purpose)
    return client, model


def _limits(**limits):
    shop = Shop.load() or Shop.objects.create(name="Loja")
    shop.ai_limits = limits
    shop.save(update_fields=["ai_limits"])


@pytest.fixture
def shop():
    return Shop.load() or Shop.objects.create(name="Loja")


def test_toda_chamada_vira_linha_com_custo_real(shop):
    configure_ai(model="claude-haiku-4-5")
    messages = FakeMessages(usage={"input_tokens": 1000, "output_tokens": 100})
    client, model = _client(messages)

    client.messages.create(model=model, max_tokens=200, messages=[{"role": "user", "content": "oi"}])

    row = AiInvocation.objects.get()
    assert (row.purpose, row.outcome, row.model) == ("copy", AiOutcome.OK, "claude-haiku-4-5")
    # Haiku 4.5: US$ 1/M entrada, US$ 5/M saída → 0,001 + 0,0005.
    assert row.cost_usd_micros == 1500
    assert row.tokens_in == 1000 and row.tokens_out == 100
    day = {d.scope: d for d in AiSpendDay.objects.all()}
    assert day["shop"].spent_usd_micros == 1500 and day["copy"].spent_usd_micros == 1500
    assert day["shop"].reserved_usd_micros == 0 and day["shop"].calls == 1


def test_kill_switch_corta_antes_de_sair(shop):
    configure_ai()
    _limits(enabled=False)

    assert not ai.is_configured("copy")
    assert "desligada" in ai.explain("copy")
    with pytest.raises(ai.AINotConfigured):
        ai.anthropic_client("copy")


def test_kill_switch_no_meio_freia_o_cliente_ja_criado(shop):
    configure_ai()
    messages = FakeMessages()
    client, model = _client(messages)
    _limits(enabled=False)

    with pytest.raises(ai_governor.AIDisabled):
        client.messages.create(model=model, max_tokens=100, messages=[])
    assert messages.calls == []
    assert AiInvocation.objects.get().outcome == AiOutcome.KILLED


def test_teto_da_loja_recusa_quando_a_reserva_nao_cabe(shop):
    configure_ai(model="claude-opus-5")
    _limits(usd_per_day=0.01)
    messages = FakeMessages()
    client, model = _client(messages)

    # Opus 5 com 4096 de saída estimada: US$ 0,10, acima do teto de US$ 0,01.
    with pytest.raises(ai_governor.AIBudgetExceeded):
        client.messages.create(model=model, max_tokens=4096, messages=[])
    assert messages.calls == []
    assert AiInvocation.objects.get().outcome == AiOutcome.BUDGET_DENIED
    assert AiSpendDay.objects.get(scope="shop").denied == 1


def test_teto_atingido_desliga_a_funcao_e_avisa(shop):
    from shopman.backstage.models import OperatorAlert

    configure_ai(model="claude-haiku-4-5")
    _limits(usd_per_day=0.002)
    client, model = _client(FakeMessages(usage={"input_tokens": 1000, "output_tokens": 300}))
    client.messages.create(model=model, max_tokens=10, messages=[])

    # Gastou US$ 0,0025: passou do teto. A próxima nem sai, e o aviso de 80% chegou.
    assert not ai.is_configured("copy")
    assert OperatorAlert.objects.filter(type="ai_budget_warning").count() == 1
    with pytest.raises(ai.AINotConfigured):
        ai.anthropic_client("copy")


def test_teto_por_funcao_nao_afeta_as_outras(shop):
    configure_ai(model="claude-haiku-4-5")
    _limits(purposes={"copy": 0.0})

    client, model = _client(FakeMessages())
    with pytest.raises(ai_governor.AIBudgetExceeded):
        client.messages.create(model=model, max_tokens=10, messages=[])
    client, model = _client(FakeMessages(), purpose="marketing")
    client.messages.create(model=model, max_tokens=10, messages=[])
    assert AiInvocation.objects.filter(purpose="marketing", outcome=AiOutcome.OK).count() == 1


def test_teto_nunca_passa_do_teto_de_codigo(shop):
    _limits(usd_per_day=3000, purposes={"copy": "9999"})
    policy = ai_governor.limits()
    assert policy.shop_usd_per_day == ai_governor.HARD_CAP_USD_PER_DAY
    assert policy.cap_usd("copy") == ai_governor.HARD_CAP_USD_PER_DAY


def test_json_torto_vale_o_padrao_nunca_sem_teto(shop):
    _limits(usd_per_day="muito", purposes=["copy"])
    policy = ai_governor.limits()
    assert policy.enabled is True
    assert policy.shop_usd_per_day == ai_governor.DEFAULT_SHOP_USD_PER_DAY
    assert policy.purposes == {}


def test_erro_do_provedor_devolve_a_reserva_e_grava_o_erro(shop):
    configure_ai(model="claude-haiku-4-5")
    client, model = _client(FakeMessages(error=TimeoutError("lento")))

    with pytest.raises(TimeoutError):
        client.messages.create(model=model, max_tokens=100, messages=[])
    row = AiInvocation.objects.get()
    assert (row.outcome, row.error_type, row.cost_usd_micros) == (AiOutcome.ERROR, "TimeoutError", 0)
    day = AiSpendDay.objects.get(scope="shop")
    assert (day.reserved_usd_micros, day.errors) == (0, 1)


def test_modelo_fora_da_tabela_conta_pelo_mais_caro(shop):
    configure_ai(model="modelo-novo")
    client, model = _client(FakeMessages(usage={"input_tokens": 1_000_000, "output_tokens": 0}))
    client.messages.create(model=model, max_tokens=1, messages=[])

    row = AiInvocation.objects.get()
    worst_in = max(p[0] for p in ai_governor.LLM_PRICES.values())
    assert row.cost_estimated is True
    assert row.cost_usd_micros == int(worst_in * 1_000_000)


def test_jev_passa_pelo_freio_e_mede_tokens(shop):
    configure_jev()
    response = mock.Mock(status_code=200)
    response.json.return_value = {"usage": {"input_tokens": 2_000_000}}
    session = mock.Mock()
    session.post.return_value = response
    url, key, model = ai.jev_endpoint(customer_text=False)

    assert ai.jev_post(session, url, key, {"q": 1}, timeout=5, model=model) is response
    session.post.assert_called_once()
    row = AiInvocation.objects.get()
    # US$ 0,042 por milhão de entrada: 2M tokens = US$ 0,084.
    assert (row.purpose, row.tokens_in, row.cost_usd_micros) == ("decision", 2_000_000, 84_000)

    _limits(enabled=False)
    with pytest.raises(ai.AINotConfigured):
        ai.jev_endpoint(customer_text=False)
