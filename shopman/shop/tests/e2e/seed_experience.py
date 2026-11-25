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
    python -m shopman.shop.tests.e2e.seed_experience --cohort CLI-005

``--cohort`` troca quem está na coorte ``internal``. A comparação A/B do OC-23
(``scripts/run_experience_compare.sh``) usa SEMPRE a mesma cliente nas jornadas
(``CLI-003``) e roda a pilha duas vezes: na rodada A ela fica fora (``--cohort
CLI-005``), na rodada B ela fica dentro (o padrão). A regra existe nas duas; só a
allow-list muda, e é o servidor que decide.

``--experiment`` (repetível) liga, além do de prova, os experimentos de verdade da
loja (os ``EXPERIMENT(<ref>)`` anotados no Nuxt), com a mesma coorte: é assim que a
comparação vê a versão B que existe, e não só a prova do mecanismo.
"""

from __future__ import annotations

import argparse
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


def params(cohort_ref: str = COHORT_CUSTOMER_REF, experiment_ref: str = EXPERIMENT_REF) -> dict:
    from django.utils import timezone

    return {
        "ref": experiment_ref,
        "surface": "storefront",
        "variants": ["a", "b"],
        "default": "a",
        "cohorts": {"internal": [cohort_ref], "pilot": []},
        "allocation": {"b": 0},
        "salt": "e2e",
        "owner": "harness E2E da loja",
        "hypothesis": "prova do mecanismo (OC-21): coorte decidida pelo servidor, sem vazar",
        "metrics": [],
        "remove_after": (timezone.localdate() + timedelta(days=30)).isoformat(),
        "generation": 1,
    }


def run(cohort_ref: str = COHORT_CUSTOMER_REF, experiments: tuple[str, ...] = ()) -> None:
    from shopman.guestman.models import Customer

    from shopman.shop.models import RuleConfig
    from shopman.shop.policies.experience import EXPERIENCE_RULE_PATH, ExperienceRule

    expected = {COHORT_CUSTOMER_REF, OUTSIDE_CUSTOMER_REF, cohort_ref}
    missing = expected - set(Customer.objects.filter(ref__in=expected).values_list("ref", flat=True))
    if missing:
        raise SystemExit(f"seed_experience: o seed não criou {sorted(missing)}; rode `manage.py seed` antes.")

    refs = [EXPERIMENT_REF, *(ref for ref in dict.fromkeys(experiments) if ref != EXPERIMENT_REF)]
    for ref in refs:
        values = params(cohort_ref, ref)
        ExperienceRule.validate_params(values)
        proof = ref == EXPERIMENT_REF
        RuleConfig.objects.update_or_create(
            ref=RULE_REF if proof else f"experience.{ref}",
            defaults={
                "rule_path": EXPERIENCE_RULE_PATH,
                "label": "Prova do harness E2E (OC-21)" if proof else f"Comparação A/B do harness E2E (OC-23): {ref}",
                "enabled": True,
                "params": values,
            },
        )
        print(f"seed_experience: '{ref}' ligado, coorte internal = {cohort_ref}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Experimento de prova do harness E2E da loja.")
    parser.add_argument("--cohort", default=COHORT_CUSTOMER_REF, help="cliente do seed na coorte internal")
    parser.add_argument(
        "--experiment",
        action="append",
        default=[],
        help="experimento da loja a ligar com a mesma coorte (repetível); o de prova vai sempre",
    )
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    run(args.cohort, tuple(args.experiment))
