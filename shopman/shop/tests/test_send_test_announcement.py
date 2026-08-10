"""O comando de teste de envio — dry-run por default, e nunca disparo em lote.

O comando fala com provedor externo de verdade, então o que precisa de teste aqui não é
a entrega (isso é a rede), e sim as travas: sem `--send` não sai nada, um telefone por
execução, e o relato distingue "o adapter recusou" de "não havia adapter".
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from shopman.shop import notifications

pytestmark = pytest.mark.django_db

PHONE = "+5543984049009"


class _Adapter:
    """Adapter de mentira que registra o que recebeu, sem tocar a rede."""

    def __init__(self, *, available: bool = True, ok: bool = True):
        self._available = available
        self._ok = ok
        self.calls: list[dict] = []

    def is_available(self, *a, **kw) -> bool:
        return self._available

    def send(self, *, recipient, template, context=None, **kw) -> bool:
        self.calls.append({"recipient": recipient, "template": template, "context": context})
        return self._ok


@pytest.fixture
def adapter(monkeypatch):
    fake = _Adapter()
    monkeypatch.setattr(notifications, "_adapters", {"sms": fake})
    # A trava de DEBUG devolveria "inerte" e o adapter nunca seria chamado.
    monkeypatch.setattr("django.conf.settings.SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG", True, raising=False)
    return fake


def _run(*args) -> str:
    out = StringIO()
    call_command("send_test_announcement", *args, stdout=out, stderr=out)
    return out.getvalue()


def test_dry_run_is_the_default(adapter):
    """A trava que mais importa: sem --send, nada sai."""
    output = _run("--phone", PHONE)

    assert adapter.calls == []
    assert "Nada foi enviado" in output


def test_send_actually_calls_the_adapter(adapter):
    output = _run("--phone", PHONE, "--send")

    assert len(adapter.calls) == 1
    assert adapter.calls[0]["recipient"] == PHONE
    assert adapter.calls[0]["template"] == "announcement.published"
    assert "aceitou o envio" in output


def test_a_list_of_phones_is_refused(adapter):
    """Este comando não é ferramenta de disparo em lote, e não vira uma por descuido."""
    with pytest.raises(CommandError, match="não faz lote"):
        _run("--phone", f"{PHONE},+5543999990001", "--send")
    assert adapter.calls == []


def test_an_unregistered_channel_says_so_instead_of_failing_obscurely(adapter):
    with pytest.raises(CommandError, match="não está registrado"):
        _run("--phone", PHONE, "--channel", "manychat", "--send")


def test_a_refusal_is_reported_as_refusal(monkeypatch):
    """Adapter que devolve False não pode virar "enviado" no relato."""
    fake = _Adapter(ok=False)
    monkeypatch.setattr(notifications, "_adapters", {"sms": fake})
    monkeypatch.setattr("django.conf.settings.SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG", True, raising=False)

    output = _run("--phone", PHONE, "--send")
    assert "recusou" in output
    assert "aceitou" not in output


def test_a_missing_credential_is_announced_before_sending(monkeypatch):
    fake = _Adapter(available=False)
    monkeypatch.setattr(notifications, "_adapters", {"sms": fake})

    output = _run("--phone", PHONE)
    assert "AUSENTE" in output


def test_the_body_of_a_real_announcement_can_be_used(adapter):
    from shopman.shop.models import Announcement, AnnouncementTemplate, Campaign, Trigger

    template = AnnouncementTemplate.objects.create(name="T", body="oi")
    rule = Campaign.objects.create(
        name="C", trigger=Trigger.MANUAL, template=template, platforms=["whatsapp"]
    )
    announcement = Announcement.objects.create(
        rule=rule, template=template, platforms=["whatsapp"],
        content={"body": "Croissant saiu do forno", "link": "/p/cro"},
    )

    _run("--phone", PHONE, "--announcement", str(announcement.pk), "--send")

    context = adapter.calls[0]["context"]
    assert context["body"] == "Croissant saiu do forno"
    assert context["action_url"] == "/p/cro"


def test_an_unknown_announcement_is_refused(adapter):
    with pytest.raises(CommandError, match="não encontrado"):
        _run("--phone", PHONE, "--announcement", "99999", "--send")
