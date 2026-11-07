from datetime import UTC, datetime
from types import SimpleNamespace

from shopman.shop.policies import ifood_concluded


def _order(channel="ifood", fact=None):
    return SimpleNamespace(channel_ref=channel, data={"ifood": {"remote_concluded": fact}} if fact is not None else {})


def test_concluded_refusal_names_the_time_and_the_verb():
    fact = {"observed_at": datetime(2026, 11, 7, 16, 0, tzinfo=UTC).isoformat()}
    refusal = ifood_concluded.concluded_refusal(_order(fact=fact), verb="recusar")
    assert refusal.startswith("O iFood já concluiu este pedido às ")
    assert refusal.endswith("Não dá mais para recusar.")


def test_concluded_refusal_is_empty_without_the_fact_or_outside_ifood():
    assert ifood_concluded.concluded_refusal(_order()) == ""
    assert ifood_concluded.concluded_refusal(_order(channel="balcao", fact={"observed_at": "x"})) == ""
    assert ifood_concluded.concluded_refusal(_order(fact={"observed_at": "not-a-date"})) == (
        "O iFood já concluiu este pedido. Não dá mais para cancelar."
    )
