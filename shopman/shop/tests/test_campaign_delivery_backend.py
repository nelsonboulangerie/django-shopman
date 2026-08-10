"""Por onde a onda de campanha realmente sai — e por onde ela NUNCA sai.

Estes testes nasceram de uma pergunta do dono: "o que acontece se eu disparar agora, e
como sei que deu certo?". Responder exigiu rodar a cadeia inteira, e ela estava
quebrada em dois pontos que nenhum teste cobria:

1. O handler chamava ``notify()`` **sem nomear backend**, e o default é ``console`` —
   registrado só em DEBUG. Em staging isso dava ``Backend not found: default`` para
   cada destinatário: a onda gravava ``sent=0, failed=N`` e ninguém recebia.
2. O status gravado era sempre ``sent``, inclusive com ``sent=0``. O painel dizia
   "enviado" ao lado de "0 enviados, 3 falharam".
"""

from __future__ import annotations

import pytest

from shopman.shop import notifications
from shopman.shop.handlers import campaign as handlers

pytestmark = pytest.mark.django_db


@pytest.fixture
def adapters(monkeypatch):
    """Controla quais backends existem, sem tocar no registro global de verdade."""
    registry: dict = {}
    monkeypatch.setattr(notifications, "_adapters", registry)
    return registry


class _Adapter:
    def __init__(self, available: bool = True):
        self._available = available

    def is_available(self, *a, **kw) -> bool:
        return self._available

    def send(self, **kwargs) -> bool:  # pragma: no cover - não exercido aqui
        return True


def test_sms_is_never_used_for_a_campaign_wave(adapters):
    """⚠️ O teste mais importante deste arquivo: consentimento é POR CANAL.

    A audiência exige consentimento de `whatsapp`. Entregar por SMS alcançaria a pessoa
    num canal que ela não autorizou — e a primeira versão desta função fazia exatamente
    isso quando o ManyChat não tinha token.
    """
    adapters["sms"] = _Adapter()
    adapters["email"] = _Adapter()

    assert handlers._whatsapp_backend() is None, "SMS e e-mail não substituem WhatsApp"


def test_manychat_wins_when_configured(adapters):
    adapters["manychat"] = _Adapter()
    adapters["console"] = _Adapter()

    assert handlers._whatsapp_backend() == "manychat"


def test_an_unconfigured_manychat_is_skipped(adapters):
    """Adapter registrado mas sem credencial não conta como transporte pronto."""
    adapters["manychat"] = _Adapter(available=False)
    adapters["console"] = _Adapter()

    assert handlers._whatsapp_backend() == "console"


def test_console_never_beats_a_real_channel(adapters):
    adapters["console"] = _Adapter()
    adapters["manychat"] = _Adapter()

    assert handlers._whatsapp_backend() == "manychat"


def test_no_backend_counts_everyone_as_failed(adapters):
    """Sem transporte, a onda é falha — nunca sucesso silencioso."""
    from types import SimpleNamespace

    announcement = SimpleNamespace(pk=1, body="oi", content={})
    recipients = (SimpleNamespace(phone="+5543999990001"), SimpleNamespace(phone="+5543999990002"))

    sent, failed = handlers._send_to(recipients, announcement=announcement)
    assert (sent, failed) == (0, 2)


def test_recipients_are_counted_once_even_as_a_generator(adapters):
    """`recipients` pode ser gerador: contá-lo duas vezes devolveria 0 na segunda."""
    from types import SimpleNamespace

    announcement = SimpleNamespace(pk=1, body="oi", content={})
    generator = (SimpleNamespace(phone=f"+554399999000{i}") for i in range(3))

    sent, failed = handlers._send_to(generator, announcement=announcement)
    assert (sent, failed) == (0, 3)


# ── O status não pode contradizer os números ao lado dele ────────────


def _announcement():
    from shopman.shop.models import Announcement, AnnouncementTemplate, Campaign, Trigger

    template = AnnouncementTemplate.objects.create(name="T", body="oi")
    rule = Campaign.objects.create(
        name="C", trigger=Trigger.MANUAL, template=template, platforms=["whatsapp"]
    )
    return Announcement.objects.create(rule=rule, template=template, platforms=["whatsapp"])


@pytest.mark.parametrize(
    ("sent", "failed", "expected"),
    [
        (3, 0, "sent"),      # tudo entregou
        (0, 3, "failed"),    # ⚠️ dizia "sent" antes — status mentindo
        (2, 1, "partial"),   # onda entrega por pessoa: parcial é resultado comum
        (0, 0, "sent"),      # onda vazia: ninguém a alcançar não é falha
    ],
)
def test_wave_status_matches_the_counts(sent, failed, expected):
    announcement = _announcement()
    handlers._record_wave(announcement, "all", sent=sent, failed=failed, expected=1)

    announcement.refresh_from_db()
    entry = announcement.platform_results["whatsapp"]
    assert entry["status"] == expected
    assert (entry["sent"], entry["failed"]) == (sent, failed)


def test_waves_accumulate_and_the_status_follows_the_total():
    """VIP entrega, geral falha: o resultado final é parcial, não 'enviado'."""
    announcement = _announcement()
    handlers._record_wave(announcement, "vip", sent=2, failed=0, expected=2)
    handlers._record_wave(announcement, "general", sent=0, failed=5, expected=2)

    announcement.refresh_from_db()
    entry = announcement.platform_results["whatsapp"]
    assert (entry["sent"], entry["failed"]) == (2, 5)
    assert entry["status"] == "partial"
