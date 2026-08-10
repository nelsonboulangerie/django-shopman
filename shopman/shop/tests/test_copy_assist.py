"""A IA que escreve para a loja: uma voz, e nunca no caminho crítico.

Dois desenhos protegidos aqui:

1. **A voz tem um dono.** Era literal no código do backstage — invisível para quem opera,
   não editável, e inexistente do lado da campanha, então catálogo e anúncio soavam como
   duas lojas. Agora é `Shop.brand_voice`, e os dois consomem.
2. **Falha da IA não trava a operação.** A fornada saiu; o anúncio dela precisa existir com
   ou sem assistente. `test_a_broken_assistant_still_produces_an_announcement` é o teste
   que mais importa neste arquivo.
"""

from __future__ import annotations

import pytest

from shopman.shop.models import AnnouncementTemplate, Campaign, Shop, Trigger
from shopman.shop.services import campaign as campaign_service
from shopman.shop.services import copy_assist

pytestmark = pytest.mark.django_db


@pytest.fixture
def configured(settings):
    settings.AI_ASSIST_API_KEY = "sk-teste"
    settings.AI_ASSIST_PROVIDER = "anthropic"
    return settings


@pytest.fixture
def template():
    return AnnouncementTemplate.objects.create(
        name="Fornada", body="{{product_name}} saiu do forno!",
        use_ai_generation=True, ai_prompt="Fale do cheiro.",
    )


def _rule(template) -> Campaign:
    return Campaign.objects.create(
        name="Fornada", trigger=Trigger.PRODUCTION_FINISHED, template=template,
        platforms=["whatsapp"],
    )


# ── A voz ────────────────────────────────────────────────────────────


def test_the_shop_voice_wins_when_configured():
    Shop.objects.create(name="Nelson", brand_voice="Fale como a Nelson fala.")
    assert copy_assist.brand_voice() == "Fale como a Nelson fala."


def test_an_empty_voice_falls_back_to_the_system_voice():
    """Loja recém-criada precisa de sugestão em português decente, não de texto sem tom."""
    Shop.objects.create(name="Nelson", brand_voice="")
    assert copy_assist.brand_voice() == copy_assist.DEFAULT_VOICE


def test_the_voice_survives_a_missing_shop():
    """Bootstrap e teste sem Shop ainda escrevem — só não com a voz da casa."""
    assert copy_assist.brand_voice() == copy_assist.DEFAULT_VOICE


def test_the_catalog_and_the_campaign_read_the_same_voice(configured, monkeypatch, template):
    """⚠️ Uma pergunta, um dono: as duas superfícies não podem divergir de tom."""
    Shop.objects.create(name="Nelson", brand_voice="A VOZ DA CASA")
    seen: list[str] = []

    def _capture(prompt, *, max_tokens=400, voice=""):
        seen.append(voice or copy_assist.brand_voice())
        return "texto"

    monkeypatch.setattr(copy_assist, "suggest", _capture)

    campaign_service._ai_body(template, {"product_name": "Croissant"})

    from shopman.offerman.models import Product

    from shopman.backstage.services import catalog as catalog_service

    # Um monkeypatch só: o catálogo importa o MESMO módulo, e é isso que o teste afirma.
    Product.objects.create(sku="CRO-001", name="Croissant", base_price_q=1200)
    catalog_service.ai_assist_field("CRO-001", "short_description")

    assert seen == ["A VOZ DA CASA", "A VOZ DA CASA"]


# ── Configuração ─────────────────────────────────────────────────────


def test_without_a_key_nothing_is_offered(settings):
    settings.AI_ASSIST_API_KEY = ""
    assert copy_assist.is_configured() is False


def test_without_a_key_asking_says_it_is_configuration_not_failure(settings):
    settings.AI_ASSIST_API_KEY = ""
    with pytest.raises(copy_assist.CopyAssistNotConfigured):
        copy_assist.suggest("escreva algo")


def test_an_unknown_provider_is_refused(settings):
    settings.AI_ASSIST_API_KEY = "sk-teste"
    settings.AI_ASSIST_PROVIDER = "papagaio"
    with pytest.raises(copy_assist.CopyAssistError):
        copy_assist.suggest("escreva algo")


# ── O leitor que faltava ─────────────────────────────────────────────


def test_the_template_switch_finally_has_a_reader(configured, monkeypatch, template):
    """`use_ai_generation` era configurável em três lugares e lido em nenhum."""
    monkeypatch.setattr(copy_assist, "suggest", lambda *a, **k: "Croissant quentinho agora.")

    announcement = campaign_service._create_announcement(_rule(template), {"sku": "CRO-001"})

    assert announcement.content["body"] == "Croissant quentinho agora."


def test_a_template_without_the_switch_is_never_sent_to_the_ai(configured, monkeypatch):
    plain = AnnouncementTemplate.objects.create(
        name="Simples", body="Saiu do forno!", use_ai_generation=False
    )
    called: list[int] = []
    monkeypatch.setattr(copy_assist, "suggest", lambda *a, **k: called.append(1) or "IA")

    announcement = campaign_service._create_announcement(_rule(plain), {"sku": "CRO-001"})

    assert announcement.content["body"] == "Saiu do forno!"
    assert called == []


def test_a_broken_assistant_still_produces_an_announcement(configured, monkeypatch, template):
    """⚠️ O teste mais importante daqui.

    A fornada saiu. O anúncio dela precisa existir com ou sem assistente — marketing não
    pode travar a operação. Mesma assimetria do agendamento que adia, e pelo mesmo motivo.
    """
    def _boom(*a, **k):
        raise copy_assist.CopyAssistError("provedor mudo")

    monkeypatch.setattr(copy_assist, "suggest", _boom)

    announcement = campaign_service._create_announcement(_rule(template), {"sku": "CRO-001"})

    # Exatamente o template renderizado: nem vazio, nem meio texto.
    assert announcement.content["body"] == "CRO-001 saiu do forno!"


def test_without_a_key_the_template_body_is_used(settings, monkeypatch, template):
    settings.AI_ASSIST_API_KEY = ""
    called: list[int] = []
    monkeypatch.setattr(copy_assist, "suggest", lambda *a, **k: called.append(1) or "IA")

    announcement = campaign_service._create_announcement(_rule(template), {"sku": "CRO-001"})

    assert called == [], "sem credencial, nem tenta"
    assert "forno" in announcement.content["body"]


def test_the_prompt_carries_the_facts_of_the_event(configured, monkeypatch, template):
    """Sem os fatos, a IA escreve propaganda genérica — e o valor do anúncio é o AGORA."""
    seen: list[str] = []
    monkeypatch.setattr(
        copy_assist, "suggest", lambda prompt, **k: seen.append(prompt) or "ok"
    )

    campaign_service._ai_body(template, {"product_name": "Croissant", "time": "07h30"})

    assert "Croissant" in seen[0]
    assert "07h30" in seen[0]
    assert "Fale do cheiro." in seen[0], "a instrução da campanha vai junto"


# ── Reescrever na revisão ────────────────────────────────────────────


def test_the_manager_can_ask_for_a_rewrite(configured, monkeypatch, template):
    monkeypatch.setattr(copy_assist, "suggest", lambda *a, **k: "Versão melhor.")
    announcement = campaign_service._create_announcement(_rule(template), {"sku": "CRO-001"})

    assert campaign_service.rewrite_body(announcement.pk) == "Versão melhor."


def test_the_rewrite_sees_what_is_on_the_screen_now(configured, monkeypatch, template):
    """O gestor pode ter editado antes de pedir: a IA melhora o texto ATUAL, não o velho."""
    seen: list[str] = []
    monkeypatch.setattr(copy_assist, "suggest", lambda prompt, **k: seen.append(prompt) or "ok")
    announcement = campaign_service._create_announcement(_rule(template), {"sku": "CRO-001"})

    campaign_service.rewrite_body(announcement.pk, current_body="Texto que eu digitei")

    # `seen[0]` é o prompt do NASCIMENTO (este modelo tem `use_ai_generation`); o da
    # reescrita é o último.
    assert "Texto que eu digitei" in seen[-1]
    assert len(seen) == 2


def test_a_published_announcement_cannot_be_rewritten(configured, monkeypatch, template):
    """Reescrever o que o cliente já leu seria mentira retroativa."""
    from shopman.shop.models import AnnouncementStatus

    monkeypatch.setattr(copy_assist, "suggest", lambda *a, **k: "nova")
    announcement = campaign_service._create_announcement(_rule(template), {"sku": "CRO-001"})
    announcement.status = AnnouncementStatus.PUBLISHED
    announcement.save(update_fields=["status"])

    with pytest.raises(campaign_service.CampaignError):
        campaign_service.rewrite_body(announcement.pk)


def test_rewriting_never_saves_by_itself(configured, monkeypatch, template):
    """Quem persiste é a aprovação. Gravar aqui tiraria do gestor a chance de descartar."""
    monkeypatch.setattr(copy_assist, "suggest", lambda *a, **k: "Versão melhor.")
    announcement = campaign_service._create_announcement(_rule(template), {"sku": "CRO-001"})
    before = announcement.content["body"]

    campaign_service.rewrite_body(announcement.pk)

    announcement.refresh_from_db()
    assert announcement.content["body"] == before
