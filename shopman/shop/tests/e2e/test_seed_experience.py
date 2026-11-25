"""OC-23: o seed do harness liga os experimentos da comparação A/B, e o servidor decide.

A comparação (``scripts/run_experience_compare.sh``) roda a pilha duas vezes com a
mesma cliente (CLI-003): na rodada A ela fica fora da coorte (``--cohort CLI-005``), na
B fica dentro. ``--experiment`` liga, além do de prova, os experimentos de verdade da
loja. Este teste prova, sem navegador, que é o RESOLVEDOR do servidor que devolve "a" ou
"b" a partir do que o seed gravou, em todos os experimentos ligados (X14: a coorte vem do
seed, nunca de query).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.test import RequestFactory
from shopman.guestman.models import Customer

from shopman.shop.models import RuleConfig
from shopman.shop.services import experience
from shopman.shop.tests.e2e import seed_experience

pytestmark = pytest.mark.django_db

REAL_EXPERIMENT = "home-recompra-no-topo"


@pytest.fixture(autouse=True)
def _seeded_customers():
    cache.clear()
    for ref in (seed_experience.COHORT_CUSTOMER_REF, seed_experience.OUTSIDE_CUSTOMER_REF):
        Customer.objects.create(ref=ref, first_name=ref)
    yield
    cache.clear()


def _variants_for(customer_ref: str) -> dict[str, str]:
    customer = Customer.objects.get(ref=customer_ref)
    request = RequestFactory().get("/api/v1/storefront/shell/")
    request.session = SessionStore()
    request.customer = SimpleNamespace(subject_id=customer.uuid)
    return {a.ref: a.variant for a in experience.resolve(request, "storefront")}


def _experience_rules() -> set[str]:
    return set(RuleConfig.objects.filter(ref__startswith="experience.").values_list("ref", flat=True))


def test_round_b_puts_the_journey_customer_in_every_experiment():
    seed_experience.run(seed_experience.COHORT_CUSTOMER_REF, (REAL_EXPERIMENT,))

    assert _experience_rules() == {seed_experience.RULE_REF, f"experience.{REAL_EXPERIMENT}"}
    assert _variants_for(seed_experience.COHORT_CUSTOMER_REF) == {
        seed_experience.EXPERIMENT_REF: "b",
        REAL_EXPERIMENT: "b",
    }
    assert _variants_for(seed_experience.OUTSIDE_CUSTOMER_REF) == {
        seed_experience.EXPERIMENT_REF: "a",
        REAL_EXPERIMENT: "a",
    }


def test_round_a_leaves_the_journey_customer_out_with_the_same_rules():
    seed_experience.run(seed_experience.OUTSIDE_CUSTOMER_REF, (REAL_EXPERIMENT,))

    assert _experience_rules() == {seed_experience.RULE_REF, f"experience.{REAL_EXPERIMENT}"}
    assert _variants_for(seed_experience.COHORT_CUSTOMER_REF) == {
        seed_experience.EXPERIMENT_REF: "a",
        REAL_EXPERIMENT: "a",
    }


def test_proof_experiment_is_always_on_and_never_duplicated():
    seed_experience.run(seed_experience.COHORT_CUSTOMER_REF, (seed_experience.EXPERIMENT_REF,))

    assert _experience_rules() == {seed_experience.RULE_REF}


def test_missing_seed_customer_stops_before_writing_any_rule():
    with pytest.raises(SystemExit, match="CLI-999"):
        seed_experience.run("CLI-999", (REAL_EXPERIMENT,))
    assert _experience_rules() == set()
