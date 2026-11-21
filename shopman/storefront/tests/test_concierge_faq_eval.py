"""O placar da resposta às perguntas frequentes (WP-18): FAQ direta × IA a partir das FAQs."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from config.management.commands.apply_search_presence import PUBLIC_FAQ
from shopman.shop.models import FAQEntry
from shopman.storefront.concierge import faq_eval
from shopman.storefront.tests import test_concierge_engine as engine

surface = engine.surface
pytestmark = pytest.mark.django_db


@pytest.fixture
def faqs(surface):
    for entry in PUBLIC_FAQ:
        FAQEntry.objects.create(
            ref=entry["ref"], question=entry["question"], answer=entry["answer"],
            search_terms=entry["search_terms"], is_published=True, position=entry["position"],
        )
    return faq_eval.live_faq("whatsapp")


class FakeClient:
    """O modelo de mentira: devolve o JSON dado e guarda o pedido."""

    def __init__(self, payload):
        self.payload = payload
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **request):
        self.requests.append(request)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(self.payload, ensure_ascii=False))],
            stop_reason="end_turn", usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )


def _case(text, parts):
    return {"ref": "t", "text": text, "parts": parts, "source": "teste"}


def test_the_model_arm_never_runs_without_paid(surface):
    with pytest.raises(CommandError, match="Nenhuma chamada foi feita"):
        call_command("concierge_faq_eval", "--arm", "model")


def test_the_direct_arm_answers_payment_and_verifies_pets(faqs):
    report = faq_eval.run(
        [_case("aceitam pix?", [["payment", "curated-quais-formas-de-pagamento-voces-aceitam"]]),
         _case("Aceitam pets ai na padaria?", [[]])],
        arm="faq", channel_ref="whatsapp",
    )
    payment, pets = report.rows
    assert payment.exact
    assert pets.exact and pets.answer.refs == [], "nenhuma FAQ de pets: o certo é verificar"


def test_a_faq_that_is_not_published_counts_as_none(surface):
    report = faq_eval.run([_case("o que é levain?", [["curated-o-que-e-fermentacao-natural"]])], arm="faq", channel_ref="whatsapp")
    assert report.rows[0].expected == [set()], "sem a FAQ publicada, a resposta certa é verificar"


def test_the_model_arm_cites_and_is_scored(faqs):
    client = FakeClient({"refs": ["payment"], "answer": "Aceitamos Pix e cartão, sim!", "uncovered": ""})

    report = faq_eval.run(
        [_case("aceitam pix?", [["payment", "curated-quais-formas-de-pagamento-voces-aceitam"]])],
        arm="model", channel_ref="whatsapp", client=client, model="deepseek-flash",
    )

    row = report.rows[0]
    assert row.exact and not row.invented
    request = client.requests[0]
    assert request["thinking"] == {"type": "disabled"}
    assert "ref: payment" in request["system"][0]["text"], "a IA recebe as FAQs vivas"


def test_a_number_that_no_cited_faq_says_is_an_invention(faqs):
    answer = faq_eval.Answer(refs=["payment"], text="Aceitamos Pix, e a entrega custa R$ 7,50.")
    assert any("7.50" in item or "7,50" in item for item in faq_eval.inventions(answer, faqs))


@pytest.mark.parametrize(
    ("answer", "flag"),
    [
        (faq_eval.Answer(refs=["nao-existe"], text="Sim."), "referência inexistente"),
        (faq_eval.Answer(refs=[], text="Aceitamos pets, sim!"), "respondeu sem citar"),
        (faq_eval.Answer(refs=["payment"], text="Pix — e cartão"), "travessão"),
    ],
)
def test_inventions_are_caught(faqs, answer, flag):
    assert any(flag in item for item in faq_eval.inventions(answer, faqs))


def test_a_part_without_faq_must_be_flagged_to_count_as_full(faqs):
    case = _case("Qual o horário de vocês no sábado? E tem estacionamento?", [["hours"], []])
    silent = faq_eval.score(case, faq_eval.Answer(refs=["hours"], text="Abrimos das 7h."), live={"hours"}, faqs=faqs, check_invention=False)
    flagged = faq_eval.score(
        case, faq_eval.Answer(refs=["hours"], text="Abrimos das 7h.", uncovered="estacionamento"),
        live={"hours"}, faqs=faqs, check_invention=False,
    )
    assert silent.exact and not silent.covered, "calou o estacionamento"
    assert flagged.covered


def test_the_golden_set_is_well_formed():
    cases = faq_eval.load_golden()
    assert len(cases) >= 20
    assert all(isinstance(c["parts"], list) and all(isinstance(p, list) for p in c["parts"]) for c in cases)
    assert sum(c["source"] == "real" for c in cases) >= 7


def test_drafts_enter_only_the_test_and_stay_unpublished(surface):
    for entry in PUBLIC_FAQ:
        FAQEntry.objects.create(
            ref=entry["ref"], question=entry["question"], answer=entry["answer"],
            search_terms=entry["search_terms"], is_published=False, position=entry["position"],
        )
    case = _case("o que é levain?", [["curated-o-que-e-fermentacao-natural"]])

    without = faq_eval.run([case], arm="faq", channel_ref="whatsapp")
    with_drafts = faq_eval.run([case], arm="faq", channel_ref="whatsapp", include_drafts=True)

    assert without.rows[0].expected == [set()], "sem a opção, rascunho não conta"
    assert with_drafts.rows[0].exact, "com a opção, a FAQ direta acha o rascunho"
    assert not FAQEntry.objects.filter(is_published=True).exists(), "nada foi publicado"
    from shopman.shop.models import Shop
    from shopman.storefront.presentation.public_information import search_public_faq

    assert not search_public_faq("levain", channel_ref="whatsapp", shop=Shop.load()), "o cliente não vê o rascunho"


def test_the_instruction_asks_to_cite_only_what_answered():
    """#2935, item 2: o braço B citava a FAQ vizinha (encomenda + horário). Cita só o que usou."""
    from shopman.storefront.concierge import faq_answer

    system = faq_answer.build_request("posso encomendar para sábado?", [], model="m")["system"][0]["text"]

    assert "só das perguntas frequentes cuja resposta você usou de fato" in system
    assert "não cite uma pergunta frequente só porque é do mesmo assunto" in system
    assert "—" not in system


def test_the_body_of_an_answer_never_picks_the_faq(surface):
    """A vizinha que respondia errado (produção, 21/11/2026): o corpo da resposta só desempata.

    "Até que horas" levava a encomenda ("24 horas de antecedência"), "me avise" levava as
    fotos ("nos avise antes"). Sem palavra na pergunta nem nos termos, não casa: vale o
    "vou verificar", que é melhor que a resposta de outra coisa.
    """
    from shopman.shop.models import Shop
    from shopman.storefront.presentation.public_information import search_public_faq

    FAQEntry.objects.create(ref="fotos", question="Posso tirar fotos na loja?", search_terms="",
                            answer="Na parte interna, pedimos que nos avise antes.", is_published=True)
    FAQEntry.objects.create(ref="encomenda", question="Posso encomendar para outro dia?", search_terms="",
                            answer="Alguns pães precisam de 24 horas de antecedência.", is_published=True)
    shop = Shop.load()

    def refs(text):
        return [a.ref for a in search_public_faq(text, channel_ref="whatsapp", shop=shop)]

    assert "curated-fotos" not in refs("me avise")
    assert "curated-encomenda" not in refs("horas")
    assert refs("tirar fotos")[:1] == ["curated-fotos"], "a pergunta casa"
    assert "curated-encomenda" in refs("antecedência encomendar"), "a pergunta casa; o corpo só soma"


def test_closing_hours_are_the_hours_question(surface):
    from shopman.shop.models import Shop
    from shopman.storefront.presentation.public_information import search_public_faq

    shop = Shop.load()
    shop.opening_hours = {"monday": {"open": "09:00", "close": "18:00"}}
    shop.save(update_fields=["opening_hours"])
    FAQEntry.objects.create(ref="pao-pronto", question="A que horas cada pão fica pronto?", search_terms="",
                            answer="O croissant fica pronto às 9h.", is_published=True)

    found = search_public_faq("fecham horas", channel_ref="whatsapp", shop=shop)

    assert found[0].ref == "hours"
