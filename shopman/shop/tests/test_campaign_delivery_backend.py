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


# ── O link leva a identidade de quem recebe ──────────────────────────
#
# ⚠️ Nasceu de um teste do dono no aparelho dele: fornada → "Eu quero" → sacola → e o
# checkout PEDIU LOGIN. A pessoa estava dentro do WhatsApp, num número que nós escolhemos
# porque sabemos de quem é. O link da campanha era o único link que a padaria mandava
# anônimo.


class _Capturing:
    """Backend que guarda o contexto de cada envio, para o teste ler o link."""

    def __init__(self):
        self.sent: list[dict] = []

    def is_available(self, *a, **kw) -> bool:
        return True

    def send(self, **kwargs) -> bool:
        self.sent.append(kwargs)
        return True


@pytest.fixture
def capturing(adapters):
    backend = _Capturing()
    adapters["manychat"] = backend
    return backend


def _wave_target(**over):
    """Anúncio-dublê: `_send_to` só lê `pk`, `body`, `content` e `expires_at`.

    Nome próprio de propósito — o `_announcement()` deste arquivo cria registro de verdade
    para os testes de status, e sobrescrevê-lo (como eu fiz na primeira versão) quebrou
    testes alheios sem nenhuma relação com este assunto.
    """
    from types import SimpleNamespace

    fields = {
        "pk": 7,
        "body": "Saiu do forno!",
        "content": {"link": "/oferta/semana-do-pao", "variables": {}},
        "expires_at": None,
    }
    fields.update(over)
    return SimpleNamespace(**fields)


def _known(customer):
    from types import SimpleNamespace

    return SimpleNamespace(
        phone=customer.phone, first_name="Ana",
        customer_ref=customer.ref, customer_uuid=str(customer.uuid),
    )


@pytest.fixture
def link_customer(db):
    from shopman.guestman.models import Customer

    return Customer.objects.create(ref="CLI-LINK", first_name="Ana", phone="+5543999997001")


def test_a_known_recipient_gets_a_personal_link(capturing, link_customer):
    """O link vai com token: o clique cai identificado, e o checkout não pergunta nada."""
    from shopman.doorman.models import AccessLink

    sent, failed = handlers._send_to((_known(link_customer),), announcement=_wave_target())

    assert (sent, failed) == (1, 0)
    url = capturing.sent[0]["context"]["action_url"]
    assert "/a?t=" in url, url
    link = AccessLink.objects.get()
    assert str(link.customer_id) == str(link_customer.uuid)
    # O destino mora no TOKEN, nunca na URL: é o que impede redirect aberto.
    assert link.metadata["next"] == "/oferta/semana-do-pao"
    assert link.metadata["login_source"] == "campaign"


def test_the_raw_token_is_never_persisted(capturing, link_customer):
    """Só o HMAC fica no banco. O token bruto existe uma vez, no caminho do envio."""
    from shopman.doorman.models import AccessLink

    handlers._send_to((_known(link_customer),), announcement=_wave_target())

    url = capturing.sent[0]["context"]["action_url"]
    raw = url.split("?t=")[1]
    stored = AccessLink.objects.get().token_hash
    assert raw not in stored
    assert len(stored) == 64


def test_each_recipient_gets_a_token_of_their_own(capturing, db):
    """Um token por pessoa: o link da Ana não serve para o João, e vice-versa."""
    from shopman.doorman.models import AccessLink
    from shopman.guestman.models import Customer

    people = [
        Customer.objects.create(ref=f"CLI-M{i}", first_name="X", phone=f"+554399999710{i}")
        for i in range(2)
    ]
    handlers._send_to(tuple(_known(c) for c in people), announcement=_wave_target())

    urls = {call["context"]["action_url"] for call in capturing.sent}
    assert len(urls) == 2
    assert AccessLink.objects.count() == 2
    assert {str(link.customer_id) for link in AccessLink.objects.all()} == {
        str(c.uuid) for c in people
    }


def test_an_anonymous_subscriber_gets_the_plain_link(capturing, db):
    """Assinante anônimo de alerta: só telefone, sem identidade a pôr no link.

    Não é exceção nem erro — é a resposta certa. E o link comum continua levando à oferta.
    """
    from types import SimpleNamespace

    from shopman.doorman.models import AccessLink

    anonymous = SimpleNamespace(phone="+5543999997200", first_name="", customer_uuid="")
    handlers._send_to((anonymous,), announcement=_wave_target())

    assert capturing.sent[0]["context"]["action_url"] == "/oferta/semana-do-pao"
    assert AccessLink.objects.count() == 0


def test_the_link_dies_with_the_announcement_window(capturing, link_customer):
    """⚠️ Prazo = janela do anúncio, não os 5 min do fluxo de login.

    Quem vê a mensagem 40 minutos depois merece o mesmo caminho; e o crachá não pode durar
    mais que a oferta que o justificou.
    """
    from datetime import timedelta

    from django.utils import timezone
    from shopman.doorman.models import AccessLink

    window = timezone.now() + timedelta(minutes=90)
    handlers._send_to((_known(link_customer),), announcement=_wave_target(expires_at=window))

    assert AccessLink.objects.get().expires_at == window


def test_an_announcement_without_a_window_still_gets_a_ceiling(capturing, link_customer):
    """Anúncio que não expira não ganha link eterno: a mensagem fica para sempre no
    aparelho, e o crachá dentro dela não pode."""
    from datetime import timedelta

    from django.utils import timezone
    from shopman.doorman.models import AccessLink

    from shopman.shop.services import campaign_identity

    handlers._send_to((_known(link_customer),), announcement=_wave_target(expires_at=None))

    expires = AccessLink.objects.get().expires_at
    assert expires <= timezone.now() + timedelta(hours=campaign_identity.MAX_HOURS)
    assert expires > timezone.now() + timedelta(hours=campaign_identity.MAX_HOURS - 1)


def test_a_failure_to_mint_never_silences_the_campaign(capturing, link_customer, monkeypatch):
    """Sem link pessoal, sai o link comum. Campanha não deixa de sair por causa disto."""
    def explode(*a, **kw):
        raise RuntimeError("banco fora")

    monkeypatch.setattr(
        "shopman.doorman.models.AccessLink.create_with_token", explode, raising=True
    )

    sent, failed = handlers._send_to((_known(link_customer),), announcement=_wave_target())

    assert (sent, failed) == (1, 0)
    assert capturing.sent[0]["context"]["action_url"] == "/oferta/semana-do-pao"


def test_an_absolute_store_link_becomes_a_relative_destination(capturing, link_customer, settings):
    """O token guarda CAMINHO. Aceitar URL absoluta ali seria abrir redirect."""
    from shopman.doorman.models import AccessLink

    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://loja.exemplo"
    target = _wave_target(content={"link": "https://loja.exemplo/produto/PAO", "variables": {}})

    handlers._send_to((_known(link_customer),), announcement=target)

    assert AccessLink.objects.get().metadata["next"] == "/produto/PAO"


def test_a_foreign_link_falls_back_to_the_cart(capturing, link_customer, settings):
    """Host que não é o nosso nunca entra no token: cai na sacola, o convite honesto."""
    from shopman.doorman.models import AccessLink

    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://loja.exemplo"
    target = _wave_target(content={"link": "https://outro.site/promo", "variables": {}})

    handlers._send_to((_known(link_customer),), announcement=target)

    assert AccessLink.objects.get().metadata["next"] == "/sacola"
