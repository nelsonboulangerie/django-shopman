"""OC-31: a mesma pergunta nunca aparece duas vezes, e a resposta que fica é a da configuração.

A home listava 34 perguntas, com "Posso encomendar para outro dia?" duas vezes: a resposta
operacional (tirada da configuração) e uma curada (``FAQEntry``) com a mesma pergunta. Duas
respostas para a mesma pergunta, de fontes diferentes, podiam se contradizer. Agora a FAQ
pública compara a pergunta sem acento, caixa, pontuação e espaço; a operacional vence; a
home mostra as 6 primeiras e "Ver todas as perguntas" leva ao resto em /faq.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.admin.sites import AdminSite

from shopman.shop.admin.faq import REPEATS_CONFIGURATION, FAQEntryAdmin
from shopman.shop.models import FAQEntry
from shopman.shop.models.faq import OPERATIONAL_QUESTIONS, normalized_question
from shopman.storefront.presentation import public_information as faq

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

PREORDER_ANSWER = "Sim. Ao finalizar o pedido, você escolhe o dia, com até 7 dias de antecedência."


@pytest.fixture
def shop(monkeypatch):
    """Loja com as sete respostas operacionais ligadas (entrega, horário, endereço,
    pagamento, encomenda, alérgenos, contato)."""
    from shopman.shop.config import ChannelConfig
    from shopman.shop.projections import checkout_context

    config = SimpleNamespace(payment=SimpleNamespace(method=["pix", "card"]), stock=SimpleNamespace(preorder=True))
    monkeypatch.setattr(ChannelConfig, "for_channel", classmethod(lambda cls, ref: config))
    monkeypatch.setattr(faq, "channel_capabilities", lambda ref: SimpleNamespace(fulfillment_types=("pickup", "delivery")))
    monkeypatch.setattr(checkout_context, "preorder_config", lambda: (7, []))
    return SimpleNamespace(
        full_address="Rua das Flores, 10",
        phone_display="(43) 3323-1997",
        email="loja@exemplo.com",
        food_safety_notice="Produzimos com trigo, leite e ovos.",
    )


def _build(shop):
    return faq.build_public_faq(
        channel_ref="web",
        shop=shop,
        status={"label": "Aberto até 19h"},
        opening_hours=({"label": "Todos os dias", "hours": "7h às 19h"},),
    )


def test_a_pergunta_normalizada_ignora_acento_caixa_pontuacao_e_espaco():
    assert normalized_question("  Posso ENCOMENDAR para outro   dia?! ") == "posso encomendar para outro dia"
    assert normalized_question("Vocês têm alérgenos?") == normalized_question("voces tem alergenos")
    assert normalized_question("Como posso pagar?") != normalized_question("Quais formas de pagamento vocês aceitam?")


def test_curada_que_repete_a_operacional_fica_de_fora_e_vale_a_configuracao(shop):
    FAQEntry.objects.create(
        question="  posso ENCOMENDAR para outro dia ",
        answer="Só com 3 dias de antecedência.",
        is_published=True,
    )

    items = _build(shop)
    matches = [item for item in items if normalized_question(item.question) == normalized_question("Posso encomendar para outro dia?")]

    assert len(matches) == 1
    assert matches[0].ref == "preorder"
    assert matches[0].answer == PREORDER_ANSWER


def test_pergunta_normalizada_nunca_aparece_duas_vezes(shop):
    # Uma curada publicada para cada pergunta operacional, escrita de outro jeito (direto no
    # banco: o ``save`` recusa as quatro reservadas, o dado legado não passou por ele), e
    # duas curadas iguais entre si.
    FAQEntry.objects.bulk_create(
        FAQEntry(
            ref=f"repete-{ref}",
            question=question.upper().replace("?", " !"),
            answer="Resposta curada que contradiz a configuração.",
            is_published=True,
            position=position,
        )
        for position, (ref, question) in enumerate(OPERATIONAL_QUESTIONS.items())
    )
    first = FAQEntry.objects.create(question="Vocês usam levain?", answer="Sim, levain.", is_published=True, position=50)
    FAQEntry.objects.create(question="voces usam levain", answer="Não.", is_published=True, position=60)

    items = _build(shop)
    keys = [normalized_question(item.question) for item in items]

    assert len(keys) == len(set(keys))
    assert [item.ref for item in items] == [*OPERATIONAL_QUESTIONS, f"curated-{first.ref}"]
    assert all(item.answer != "Resposta curada que contradiz a configuração." for item in items)
    assert next(item for item in items if item.ref == f"curated-{first.ref}").answer == "Sim, levain."


def test_a_busca_da_concierge_nao_devolve_a_resposta_repetida(shop, monkeypatch):
    FAQEntry.objects.create(question="Posso encomendar para outro dia?", answer="Não.", is_published=True)
    items = _build(shop)
    monkeypatch.setattr(faq, "build_public_faq", lambda **kwargs: items)

    found = faq.search_public_faq("encomendar para outro dia", channel_ref="web", shop=shop)

    assert [item.answer for item in found if "outro dia" in item.question] == [PREORDER_ANSWER]


def test_home_mostra_as_6_primeiras_e_o_resto_fica_na_faq(rf):
    from django.core.cache import cache

    from shopman.shop.models import Shop
    from shopman.shop.models.shop import SHOP_CACHE_KEY
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.presentation.home import build_home, build_shell

    shop = Shop.load() or Shop.objects.create(name="Test Padaria")
    shop.opening_hours = {day: {"open": "07:00", "close": "19:00"} for day in ("monday", "saturday")}
    shop.save()
    cache.delete(SHOP_CACHE_KEY)
    for position in range(8):
        FAQEntry.objects.create(question=f"Pergunta curada {position}?", answer="Sim.", is_published=True, position=position)

    request = rf.get("/api/v1/storefront/home/")
    full = projection_data(build_shell(request))["faq"]
    on_home = projection_data(build_home(request))["faq"]

    assert faq.HOME_FAQ_LIMIT == 6
    assert len(full) > 6
    # As mais úteis: as primeiras na ordem da FAQ (operacionais, depois curadas pela
    # posição). A lista inteira continua no shell e no site, que alimentam /faq.
    assert on_home == full[:6]


def test_admin_avisa_a_curada_que_repete_a_configuracao():
    admin = FAQEntryAdmin(FAQEntry, AdminSite())
    repeated = FAQEntry.objects.create(question="posso encomendar para outro dia", answer="Não.")
    own = FAQEntry.objects.create(question="Vocês usam levain?", answer="Sim.", is_published=True, position=1)
    twin = FAQEntry.objects.create(question="Vocês usam LEVAIN", answer="Não.", is_published=True, position=2)

    assert admin.repeats_label(repeated) == REPEATS_CONFIGURATION
    assert admin.repeats_label(own) == ""
    assert admin.repetition(repeated) == (
        "Repete “Posso encomendar para outro dia?”, que a loja já responde pela configuração. "
        "O site mostra só a resposta da configuração, e esta fica de fora. Se o assunto é outro, "
        "reescreva a pergunta."
    )
    assert admin.repetition(own) == "Não repete outra pergunta."
    assert admin.repetition(twin) == (
        "Repete “Vocês usam levain?”, outra pergunta publicada que vem antes na ordem. O site mostra só a primeira."
    )
    assert "—" not in admin.repetition(repeated) + admin.repetition(twin)
