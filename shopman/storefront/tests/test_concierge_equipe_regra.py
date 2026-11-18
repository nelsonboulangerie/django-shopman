"""Equipe achada pela regra local, sem modelo (WP-04 do plano da Concierge).

Cada padrão de linguagem novo tem a frase que dispara e a frase parecida que não pode
disparar. As mesmas frases de reclamação e pedido de pessoa estão nos exemplos da R4
(``house_rules.py``); aqui elas são medidas uma a uma, junto com o placar do conjunto.
"""

from __future__ import annotations

import pytest

from shopman.storefront.concierge import reply_eval
from shopman.storefront.concierge.handoff import TEAM_CATEGORIES, classify_handoff_request
from shopman.storefront.concierge.house_rules import RULES
from shopman.storefront.concierge.triage import classify_rules

pytestmark = pytest.mark.django_db

# (padrão, fala que dispara, fala parecida que não pode disparar)
_TEAM = (
    ("pessoa sem 'de verdade'", "Quero falar com uma pessoa, mas antes: vocês abrem amanhã?",
     "O bolo serve quantas pessoas?"),
    ("como o cliente se sentiu", "Você não tem sentimentos! Me senti ofendido…",
     "Fiquei curiosa com o pão de fermentação natural"),
    ("como o cliente se sentiu", "Fiquei bem chateada com o atendimento",
     "Estou com pressa, tem croissant?"),
    ("mau trato com nome", "Que falta de respeito", "Respeito a escolha, fico com o integral"),
    ("cobrança da demora", "Oi tudo bem? Porque demorou tanto pra responder?",
     "Quanto tempo demora a entrega?"),
    ("cobrança da demora", "O pedido demorou demais", "Demora muito para ficar pronto?"),
    ("cobrança da demora", "Ninguém me respondeu até agora", "Me responde quando puder: tem baguete?"),
    ("conta do que a casa fez", "Porque me ofereceu Fendu que está indisponível, criatura?",
     "Porque me disseram que vocês fazem bolo, fazem?"),
    ("conta do que a casa fez", "Por que me cobraram duas vezes?",
     "Por que o croissant de vocês é tão bom?"),
    ("produto com defeito", "O pão veio mofado", "O pão de queijo vem cru para assar em casa?"),
    ("produto com defeito", "O croissant chegou murcho", "O croissant chega quente?"),
    ("diferente do de sempre",
     "Porque não sei .. eu sempre pego o de brioche e este de hambúrguer estava diferente desta vez",
     "O pão italiano é diferente do francês?"),
    ("diferente do de sempre", "O sabor está diferente do normal", "Tem algum sabor diferente hoje?"),
)


@pytest.mark.parametrize(("pattern", "fires", "_quiet"), _TEAM, ids=[f"{p}+" for p, *_ in _TEAM])
def test_the_pattern_sends_to_the_team(pattern, fires, _quiet):
    assert classify_handoff_request(fires) in TEAM_CATEGORIES, pattern


@pytest.mark.parametrize(("pattern", "_fires", "quiet"), _TEAM, ids=[f"{p}-" for p, *_ in _TEAM])
def test_the_similar_phrase_stays_with_the_concierge(pattern, _fires, quiet):
    assert classify_handoff_request(quiet) == "", pattern


@pytest.mark.parametrize(("fires", "quiet"), (
    ("Olá, me chamo Ana e tenho uma empresa que fornece sacos para lixo, gostaria de falar com o setor de compras",
     "Quero comprar dois croissants"),
    ("Quem é o responsável pelas compras da padaria?", "Comprei ontem o pão de campanha, tem hoje?"),
))
def test_who_sells_to_the_house_goes_to_the_other_desk(fires, quiet):
    assert classify_rules(fires)[0] == "supplier_offer"
    assert classify_rules(quiet)[0] != "supplier_offer"


def test_every_team_phrase_here_is_also_an_r4_example():
    r4 = next(rule for rule in RULES if rule.id == "R4")
    lowered = {phrase.casefold() for phrase in (*r4.entry_flag, *r4.entry_pass)}
    # Os exemplos da R4 cobrem cada padrão; a tabela é medida por inteiro no placar.
    patterns_in_r4 = {
        "pessoa sem 'de verdade'": "quero falar com uma pessoa",
        "como o cliente se sentiu": "me senti ofendida com a resposta",
        "mau trato com nome": "que falta de respeito",
        "cobrança da demora": "por que demorou tanto pra responder?",
        "conta do que a casa fez": "por que me cobraram duas vezes?",
        "produto com defeito": "o pão veio mofado",
        "diferente do de sempre": "o sabor está diferente do normal",
    }
    assert {pattern for pattern, *_ in _TEAM} == set(patterns_in_r4)
    assert set(patterns_in_r4.values()) <= lowered


def test_the_golden_set_team_is_found_without_the_model():
    report = reply_eval.run(reply_eval.load_golden(), classifier="rules")
    sensitive = [r for r in report.results if r.expected["destination"] != "answer"]
    plain = [r for r in report.results if r.expected["destination"] == "answer"]
    assert sum(r.destination_ok for r in sensitive) >= 10, f"equipe achada {sum(r.destination_ok for r in sensitive)}/13"
    assert sum(not r.destination_ok for r in plain) <= 3


def test_the_golden_set_team_is_found_by_the_local_parts_reading():
    report = reply_eval.run_plural(reply_eval.load_golden(), reader="local")
    sensitive = [r for r in report.results if r.case["expected"]["destination"] != "answer"]
    plain = [r for r in report.results if r.case["expected"]["destination"] == "answer"]
    assert sum(r.team_after for r in sensitive) >= 10
    assert sum(r.team_after for r in plain) <= 4
