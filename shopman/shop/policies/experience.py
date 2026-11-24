"""Experimento de experiência: qual versão de uma superfície cada pessoa vê (R4 do release).

Uma linha de ``RuleConfig`` por experimento, com
``rule_path = "shopman.shop.rules.experience.ExperienceRule"``. A regra NÃO decide
nada sozinha: ela descreve o experimento e confere a própria configuração antes de
o save passar (``RuleConfig.clean`` chama ``validate_params``). Quem decide a versão
de cada requisição é ``shopman.shop.services.experience.resolve``.

Onde mora: a política nasce em ``policies/`` (trava do inventário do orquestrador,
``scripts/check_orchestrator_units.py``), e ``shopman/shop/rules/experience.py`` a
expõe no registro de regras, que é onde o ``rule_path`` aponta (a lista de módulos
autorizados é ``shopman.shop.rules.*``).

Por que ``RuleConfig`` e não um painel novo (WP-RELEASE-01 D5, ADR-043 item 7,
``docs/reference/release-contract.md`` "Coortes e flags"): ela já é por loja, já tem
histórico (``simple_history``), já tem permissão (``shop.manage_rules``) e já tem o
interruptor que é o kill switch (``enabled``). Um segundo control plane só nasce com
o gap provado em ADR.

O que a regra recusa, e por quê:

- ``remove_after`` ausente ou a mais de 90 dias: versão paralela permanente é dívida
  (WP-RELEASE-01, invariante 14). Data no passado é ACEITA no save, de propósito:
  desligar uma regra vencida é um save, e o kill switch nunca pode ser recusado. A
  regra vencida resolve o padrão e avisa o operador; a CI reprova o vencido no seed
  (``scripts/check_experiments.py``).
- alocação percentual diferente de zero: nenhum cliente nas coortes por ora
  (decisão D2 do dono, 23/11/2026). A chave existe para o dia em que mudar.
- coorte desconhecida: as coortes são nomeadas (``internal``, ``pilot``), nunca um
  rótulo livre que ninguém lê.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from shopman.shop.rules import BaseRule

#: O ``rule_path`` que o resolvedor procura entre as regras ativas.
EXPERIENCE_RULE_PATH = "shopman.shop.rules.experience.ExperienceRule"

#: Teto de vida de um experimento, contado do dia em que a regra é salva.
MAX_LIFETIME_DAYS = 90

#: As coortes nomeadas (D5). ``off`` é a regra desligada e ``default`` é todo mundo
#: no padrão: nenhuma das duas é uma lista de pessoas.
COHORTS = ("internal", "pilot")

_SLUG = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")

REQUIRED = ("ref", "surface", "variants", "default", "owner", "hypothesis", "remove_after")
KNOWN = frozenset({
    *REQUIRED,
    "cohorts",
    "allocation",
    "salt",
    "metrics",
    "generation",
    "environments",
})


class ExperienceRuleError(ValueError):
    """Configuração de experimento que o esquema recusa. A mensagem vai para o Admin."""


def parse_remove_after(value) -> date:
    """A data de ``remove_after`` (``AAAA-MM-DD``), ou ``ExperienceRuleError``."""
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ExperienceRuleError(
            f"'remove_after' é uma data AAAA-MM-DD; veio {value!r}."
        ) from exc


def _today() -> date:
    from django.utils import timezone

    return timezone.localdate()


class ExperienceRule(BaseRule):
    """Um experimento de experiência: variantes, coortes, dono, hipótese e prazo."""

    code = "experience"
    label = "Experimento de experiência"
    # Não é validator nem pricing: o resolvedor a LÊ pelas regras ativas, e o
    # registry do Orderman não deve registrá-la como nada.
    rule_type = "experience"

    def __init__(self, **params):
        self.validate_params(params)
        self.params = dict(params)

    @classmethod
    def validate_params(cls, params: dict) -> None:
        if not isinstance(params, dict):
            raise ExperienceRuleError("Os parâmetros do experimento são um objeto.")
        unknown = sorted(set(params) - KNOWN)
        if unknown:
            raise ExperienceRuleError(
                f"Chave(s) que o esquema não conhece: {', '.join(unknown)}. "
                f"O esquema é: {', '.join(sorted(KNOWN))}."
            )
        missing = [key for key in REQUIRED if params.get(key) in (None, "", [])]
        if missing:
            raise ExperienceRuleError(f"Falta no experimento: {', '.join(missing)}.")

        for key in ("ref", "surface"):
            if not isinstance(params[key], str) or not _SLUG.match(params[key]):
                raise ExperienceRuleError(
                    f"'{key}' é um identificador em minúsculas, com hífen ou sublinhado."
                )

        variants = params["variants"]
        if (
            not isinstance(variants, list)
            or len(variants) != 2
            or any(not isinstance(v, str) or not _SLUG.match(v) for v in variants)
            or len(set(variants)) != len(variants)
        ):
            # Duas, e só duas: quem está numa coorte vê A OUTRA. Com três variantes a
            # coorte precisaria dizer qual, e o esquema ainda não tem onde.
            raise ExperienceRuleError("'variants' são exatamente duas versões distintas, como [\"a\", \"b\"].")
        if params["default"] not in variants:
            raise ExperienceRuleError("'default' precisa ser uma das 'variants'.")

        for key in ("owner", "hypothesis"):
            if not isinstance(params[key], str) or not params[key].strip():
                raise ExperienceRuleError(f"'{key}' é um texto não vazio.")

        remove_after = parse_remove_after(params["remove_after"])
        limit = _today() + timedelta(days=MAX_LIFETIME_DAYS)
        if remove_after > limit:
            raise ExperienceRuleError(
                f"'remove_after' fica no máximo {MAX_LIFETIME_DAYS} dias à frente "
                f"(até {limit.isoformat()})."
            )

        cohorts = params.get("cohorts") or {}
        if not isinstance(cohorts, dict):
            raise ExperienceRuleError("'cohorts' é um objeto {coorte: [códigos de cliente]}.")
        extra = sorted(set(cohorts) - set(COHORTS))
        if extra:
            raise ExperienceRuleError(
                f"Coorte(s) desconhecida(s): {', '.join(extra)}. As coortes são: {', '.join(COHORTS)}."
            )
        for name, members in cohorts.items():
            if not isinstance(members, list) or any(
                not isinstance(m, str) or not m.strip() for m in members
            ):
                raise ExperienceRuleError(f"cohorts.{name} é uma lista de códigos de cliente.")

        allocation = params.get("allocation") or {}
        if not isinstance(allocation, dict):
            raise ExperienceRuleError("'allocation' é um objeto {variante: percentual}.")
        for variant, percent in allocation.items():
            if variant not in variants:
                raise ExperienceRuleError(f"allocation.{variant}: não é uma das 'variants'.")
            if isinstance(percent, bool) or not isinstance(percent, (int, float)) or percent != 0:
                raise ExperienceRuleError(
                    f"allocation.{variant}: a alocação por percentual está fora por ora "
                    "(nenhum cliente nas coortes, decisão D2); use 0."
                )

        salt = params.get("salt")
        if salt is not None and not isinstance(salt, str):
            raise ExperienceRuleError("'salt' é um texto.")

        metrics = params.get("metrics") or []
        if not isinstance(metrics, list) or any(not isinstance(m, str) or not m.strip() for m in metrics):
            raise ExperienceRuleError("'metrics' é uma lista de nomes de métrica.")

        generation = params.get("generation", 1)
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise ExperienceRuleError("'generation' é um inteiro a partir de 1.")

        environments = params.get("environments")
        if environments is not None:
            from shopman.shop.environment import (
                NON_PRODUCTION_ENVIRONMENTS,
                PRODUCTION_ENVIRONMENTS,
            )

            known = NON_PRODUCTION_ENVIRONMENTS | PRODUCTION_ENVIRONMENTS
            if not isinstance(environments, list) or not environments or any(
                not isinstance(e, str) or e.strip().lower() not in known for e in environments
            ):
                raise ExperienceRuleError(
                    "'environments' é uma lista de ambientes conhecidos "
                    f"({', '.join(sorted(known))}); omita para valer em todos."
                )
