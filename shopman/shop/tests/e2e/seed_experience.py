"""Experimento de prova do harness E2E da loja (OC-21, X14). Só do harness.

A coorte é forçada PELO SERVIDOR, como na vida real (decisão D1 do dono): uma
``RuleConfig`` de ``ExperienceRule`` com um cliente do seed na allow-list
``internal``. Nenhuma query, cabeçalho ou cookie escolhe a versão, e o teste
(``test_experience_e2e.py``) só entra como cliente e olha o que a loja devolve.

Roda ANTES de o Django do harness subir (``scripts/run_storefront_e2e.sh``): sem
Redis, o cache das regras é por processo (``rules/engine.py``, uma hora), e uma
regra criada pelo processo do teste com o servidor já de pé não seria vista.

Nunca entra no ``seed`` da loja: é um experimento de mentira, com prazo calculado
(nunca vence no seed, ``scripts/check_experiments.py``).

    python -m shopman.shop.tests.e2e.seed_experience
"""

from __future__ import annotations

import os
from datetime import timedelta

#: O experimento que a loja vê no shell (``experience: [{ref, variant}]``).
EXPERIMENT_REF = "prova-e2e"
RULE_REF = "experience.prova-e2e"
#: Quem está na coorte (vê "b") e quem está fora (vê "a"): clientes do ``seed``.
COHORT_CUSTOMER_REF = "CLI-003"
COHORT_CUSTOMER_PHONE = "43993333333"
OUTSIDE_CUSTOMER_REF = "CLI-005"
OUTSIDE_CUSTOMER_PHONE = "43995555555"


def params() -> dict:
    from django.utils import timezone

    return {
        "ref": EXPERIMENT_REF,
        "surface": "storefront",
        "variants": ["a", "b"],
        "default": "a",
        "cohorts": {"internal": [COHORT_CUSTOMER_REF], "pilot": []},
        "allocation": {"b": 0},
        "salt": "e2e",
        "owner": "harness E2E da loja",
        "hypothesis": "prova do mecanismo (OC-21): coorte decidida pelo servidor, sem vazar",
        "metrics": [],
        "remove_after": (timezone.localdate() + timedelta(days=30)).isoformat(),
        "generation": 1,
    }


def run() -> None:
    from shopman.guestman.models import Customer

    from shopman.shop.models import RuleConfig
    from shopman.shop.policies.experience import EXPERIENCE_RULE_PATH, ExperienceRule

    missing = {COHORT_CUSTOMER_REF, OUTSIDE_CUSTOMER_REF} - set(
        Customer.objects.filter(ref__in=[COHORT_CUSTOMER_REF, OUTSIDE_CUSTOMER_REF]).values_list("ref", flat=True)
    )
    if missing:
        raise SystemExit(f"seed_experience: o seed não criou {sorted(missing)}; rode `manage.py seed` antes.")

    values = params()
    ExperienceRule.validate_params(values)
    RuleConfig.objects.update_or_create(
        ref=RULE_REF,
        defaults={
            "rule_path": EXPERIENCE_RULE_PATH,
            "label": "Prova do harness E2E (OC-21)",
            "enabled": True,
            "params": values,
        },
    )
    print(f"seed_experience: '{EXPERIMENT_REF}' ligado, coorte internal = {COHORT_CUSTOMER_REF}.")


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    run()
