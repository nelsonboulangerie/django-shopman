"""As regras de sugestão — configuráveis, não fixas em atributo.

O motor **não conhece** natureza, sabor ou temperatura. Ele lê duas regras da
família ``RuleConfig`` e obedece ao que elas dizem; atributo novo no Admin
amplia o vocabulário das regras sem deploy. É a diferença entre "a casa decidiu
que doce pede café" morar no código e morar na configuração.

⚠️ **Regra em branco não quebra nada.** Sem pareamento cadastrado o adicional
roda só com co-ocorrência e portões — cada atributo cadastrado acrescenta sinal,
nenhum é pré-requisito.

⚠️ **O esquema é só isto: parear, exigir, preferir, aproximar, pesar, filtrar
por contexto e limitar por superfície.** Regra que precise de mais virou lógica,
e lógica vai para código com teste. O Admin não é editor de fluxo — foi o
ManyChat que ensinou o preço disso.

## suggestion.complement

```python
{
  "pairings": [
    # when: a SACOLA tem cada condição (em qualquer item);
    # when_absent: a sacola NÃO tem nenhuma destas;
    # suggest: o CANDIDATO satisfaz todas. Cada lado é objeto ou lista.
    {"when": {"attr": "sabor", "value": "salgado"},
     "when_absent": [{"attr": "natureza", "value": "bebida"}],
     "suggest": [{"attr": "natureza", "value": "bebida"},
                 {"attr": "temperatura", "value": "gelado"}],
     "weight": 2},
    {"when": {"attr": "sabor", "value": "doce"}, "suggest": {"tag": "cafe"}, "weight": 2},
  ],
  "affinity_weight": 3,          # 0 desliga; o histórico só desempata
  "distinct_from_cart": ["natureza", "sabor"],
  "one_per_cart": [{"attr": "natureza", "value": "bebida"}],
  "price": "below_cart_average",
  "context": {"delivery": {"exclude": {"attr": "temperatura", "value": "gelado"}}},
  "per_surface": {"web": 1, "concierge": 1},
}
```

## suggestion.substitute

```python
{
  "must_match": ["sabor"],
  "prefer": ["collection"],
  "approximate": ["peso_unidade_g"],
  "price_band": 0.30,
  "cross_collection_when_empty": True,
}
```

A validação recusa atributo ou opção que não existe no registro — é o que
impede uma regra de citar ``sabour`` e falhar em silêncio para sempre.

``distinct_from_cart`` é portão: o adicional não pode ter os mesmos valores
que um item da sacola em TODOS esses atributos (croque não sugere croque). A
coleção primária igual também exclui, e essa não é configurável — é a definição
de complemento, não uma preferência da casa. ``one_per_cart`` também é portão:
se a sacola já tem um item daquela classe, outro da mesma classe não é
oferecido ("bebida com bebida acho que não", dono, 23/09).
"""

from __future__ import annotations

import logging

from shopman.shop.rules import BaseRule

logger = logging.getLogger(__name__)

COMPLEMENT_REF = "suggestion.complement"
SUBSTITUTE_REF = "suggestion.substitute"

#: O que ``price`` aceita. Preferência, não portão: os portões estão no motor
#: (visível, vendável, disponível, fora da sacola) e preço não é um deles — um
#: filtro duro de preço calaria a sugestão numa sacola barata.
PRICE_POLICIES = ("below_cart_average",)

#: O que ``prefer`` e ``approximate`` aceitam além de um ref de atributo.
NON_ATTRIBUTE_SIGNALS = ("collection", "keywords", "name")


#: Os critérios do dono (04/09, refeitos em 23/09). Vivem aqui, e não só na
#: migração, porque o `seed --flush` apaga TODA `RuleConfig` e precisa saber
#: reconstruí-las — a migração cobre quem já está no ar, o seed cobre quem
#: reconstrói do zero. As migrações guardam cópias congeladas; o teste
#: `test_the_migration_and_the_seed_agree_on_the_defaults` compara as duas.
#:
#: Em palavras (dono, 23/09): "a primeira frente de sugestão de complemento
#: deve ser bebida com comida e comida com bebida"; bebida quente + doce e
#: bebida gelada + salgado "são preferenciais, mas não devem excluir
#: cruzamentos diferentes"; "bebida com bebida acho que não"; "se já tem
#: salgado e já tem bebida, oferece um doce, claro!".
#:
#: Pesos: a FRENTE vale 3 e a PREFERÊNCIA soma 1 ou 2 por cima — o cruzado
#: (salgado + bebida quente) continua elegível, só perde. Histórico e preço
#: desempatam abaixo de 1 (ver `AFFINITY_TIEBREAK` no motor) e não invertem
#: nada disso.
_NO_DRINK = [{"attr": "natureza", "value": "bebida"}]
_NO_FOOD = [{"attr": "natureza", "value": "comida"}]

DEFAULT_COMPLEMENT_PARAMS = {
    "pairings": [
        # 1ª frente, sacola só de comida → bebida.
        {"when": {"attr": "natureza", "value": "comida"}, "when_absent": _NO_DRINK,
         "suggest": {"attr": "natureza", "value": "bebida"}, "weight": 3},
        {"when": {"attr": "sabor", "value": "salgado"}, "when_absent": _NO_DRINK,
         "suggest": [{"attr": "natureza", "value": "bebida"},
                     {"attr": "temperatura", "value": "gelado"}], "weight": 2},
        {"when": {"attr": "sabor", "value": "doce"}, "when_absent": _NO_DRINK,
         "suggest": [{"attr": "natureza", "value": "bebida"},
                     {"attr": "temperatura", "value": "quente"}], "weight": 2},
        # Pão, folhado e doce de vitrine (temperatura ambiente) pedem o café;
        # é o que cobre o folhado, cujo sabor a coleção não responde.
        {"when": {"attr": "temperatura", "value": "ambiente"}, "when_absent": _NO_DRINK,
         "suggest": [{"attr": "natureza", "value": "bebida"},
                     {"attr": "temperatura", "value": "quente"}], "weight": 1},
        # 1ª frente, o espelho: sacola só de bebida → comida.
        {"when": {"attr": "natureza", "value": "bebida"}, "when_absent": _NO_FOOD,
         "suggest": {"attr": "natureza", "value": "comida"}, "weight": 3},
        {"when": {"attr": "temperatura", "value": "quente"}, "when_absent": _NO_FOOD,
         "suggest": {"attr": "sabor", "value": "doce"}, "weight": 2},
        {"when": {"attr": "temperatura", "value": "gelado"}, "when_absent": _NO_FOOD,
         "suggest": {"attr": "sabor", "value": "salgado"}, "weight": 2},
        # 2ª frente, comida + bebida → o que falta na mesa.
        {"when": [{"attr": "sabor", "value": "salgado"}, {"attr": "natureza", "value": "bebida"}],
         "suggest": {"attr": "sabor", "value": "doce"}, "weight": 3},
        {"when": [{"attr": "natureza", "value": "comida"}, {"attr": "natureza", "value": "bebida"}],
         "suggest": {"attr": "sabor", "value": "doce"}, "weight": 1},
        # Doce + bebida: o café da manhã está completo; o convite é o pão para
        # levar, e fraco (default de 23/09, pergunta aberta ao dono). Com
        # salgado também na mesa, ela está completa e o motor se cala.
        # `tag: pao` porque "neutro" também é o brioche de chocolate, que a
        # coleção (macios) não distingue do pão de forma.
        {"when": [{"attr": "sabor", "value": "doce"}, {"attr": "natureza", "value": "bebida"}],
         "when_absent": [{"attr": "sabor", "value": "salgado"}],
         "suggest": [{"attr": "sabor", "value": "neutro"}, {"tag": "pao"}], "weight": 1},
        # Pão pede o que se passa nele (manteiga, geleia) — abaixo da bebida.
        {"when": {"attr": "sabor", "value": "neutro"},
         "suggest": {"attr": "natureza", "value": "acompanhamento"}, "weight": 2},
        # Catálogo sem bebida disponível: salgado ainda tem o doce.
        {"when": {"attr": "sabor", "value": "salgado"},
         "suggest": {"attr": "sabor", "value": "doce"}, "weight": 1},
    ],
    "affinity_weight": 3,
    # Adicional é complemento, não substituto: nada com a mesma natureza E o
    # mesmo sabor de um item da sacola (croque não sugere croque — 23/09).
    "distinct_from_cart": ["natureza", "sabor"],
    # "Bebida com bebida acho que não" (dono, 23/09).
    "one_per_cart": [{"attr": "natureza", "value": "bebida"}],
    "price": "below_cart_average",
    "per_surface": {"web": 1, "concierge": 1},
}

#: O motor de substituto é da F2. A regra nasce cadastrada e DESLIGADA: o gestor
#: já vê a política, a validação já recusa erro de digitação, e nada a lê ainda.
DEFAULT_SUBSTITUTE_PARAMS = {
    "must_match": ["sabor"],            # doce → doce, salgado → salgado é fronteira
    "prefer": ["collection"],           # dentro da coleção primeiro
    "approximate": ["peso_unidade_g"],  # o mais próximo ganha, sem faixa
    "price_band": 0.30,
    "cross_collection_when_empty": True,
}


class SuggestionRuleError(ValueError):
    """Configuração que o esquema recusa. A mensagem vai para o Admin."""


def _known_attributes() -> dict:
    """``{ref: definição}`` do registro, ou ``{}`` se ele ainda não existe.

    Vazio quando o banco não está pronto (boot, migração): a validação
    estrutural continua valendo, e a semântica volta no próximo save. Só isso
    justifica engolir a falha aqui — e mesmo assim ela vai para o log, porque
    uma validação que se desliga em silêncio é uma validação que não existe.
    """
    from django.db import OperationalError, ProgrammingError

    try:
        from shopman.shop.services import attributes

        return {d.ref: d for d in attributes.registry()}
    except (OperationalError, ProgrammingError):
        # Tabela ainda não migrada: condição de boot, esperada.
        logger.debug("suggestion: registro de atributos indisponível; validando só a forma.")
        return {}
    except Exception:
        logger.warning(
            "suggestion: registro de atributos ilegível; validando só a forma.", exc_info=True,
        )
        return {}


def _check_attribute(ref, values, *, where: str) -> None:
    known = _known_attributes()
    if not known:
        return
    if ref not in known:
        raise SuggestionRuleError(
            f"{where}: o atributo '{ref}' não existe no registro. "
            f"Conheço: {', '.join(sorted(known))}."
        )
    definition = known[ref]
    if not definition.is_choice:
        return
    allowed = definition.option_values()
    for value in values:
        if str(value) not in allowed:
            raise SuggestionRuleError(
                f"{where}: '{value}' não é opção de '{ref}'. Use: {', '.join(allowed)}."
            )


def _check_conditions(side, *, where: str, allow_tag: bool, required: bool = True) -> None:
    """Um lado do pareamento: um objeto-condição ou uma lista não vazia deles."""
    if isinstance(side, list):
        if not side:
            raise SuggestionRuleError(f"{where}: a lista de condições está vazia.")
        for j, condition in enumerate(side, start=1):
            _check_side(condition, where=f"{where}[{j}]", allow_tag=allow_tag)
        return
    if side is None and not required:
        return
    _check_side(side, where=where, allow_tag=allow_tag)


def _check_side(side: dict, *, where: str, allow_tag: bool) -> None:
    if not isinstance(side, dict):
        raise SuggestionRuleError(f"{where}: esperava um objeto.")

    if "tag" in side:
        if not allow_tag:
            raise SuggestionRuleError(f"{where}: 'tag' só vale do lado sugerido.")
        if not str(side["tag"]).strip():
            raise SuggestionRuleError(f"{where}: 'tag' vazia.")
        return

    ref = side.get("attr")
    if not ref:
        raise SuggestionRuleError(f"{where}: falta 'attr' (ou 'tag').")

    if "value" in side and "in" in side:
        raise SuggestionRuleError(f"{where}: use 'value' OU 'in', não os dois.")
    if "in" in side:
        values = side["in"]
        if not isinstance(values, list) or not values:
            raise SuggestionRuleError(f"{where}: 'in' precisa ser uma lista não vazia.")
    elif "value" in side:
        values = [side["value"]]
    else:
        raise SuggestionRuleError(f"{where}: falta 'value' ou 'in'.")

    _check_attribute(ref, values, where=where)


class ComplementRule(BaseRule):
    """``suggestion.complement`` — o que oferecer junto do que já está na sacola."""

    code = COMPLEMENT_REF
    label = "Sugestão de adicional"
    # Não é validator nem pricing: o motor a LÊ por `get_rule_params`, e o
    # registry do Orderman não deve registrá-la como nada.
    rule_type = "suggestion"

    KNOWN = frozenset({
        "pairings", "affinity_weight", "distinct_from_cart", "one_per_cart",
        "price", "context", "per_surface",
    })

    def __init__(self, **params):
        self.params = dict(params)
        self.validate_params(self.params)

    @classmethod
    def validate_params(cls, params: dict) -> None:
        unknown = sorted(set(params) - cls.KNOWN)
        if unknown:
            raise SuggestionRuleError(
                f"Chave(s) que o esquema não conhece: {', '.join(unknown)}. "
                f"O esquema é: {', '.join(sorted(cls.KNOWN))}."
            )

        pairings = params.get("pairings") or []
        if not isinstance(pairings, list):
            raise SuggestionRuleError("'pairings' precisa ser uma lista.")
        for i, pairing in enumerate(pairings, start=1):
            where = f"pareamento {i}"
            if not isinstance(pairing, dict):
                raise SuggestionRuleError(f"{where}: esperava um objeto.")
            extra = sorted(set(pairing) - {"when", "when_absent", "suggest", "weight"})
            if extra:
                raise SuggestionRuleError(f"{where}: chave(s) desconhecida(s): {', '.join(extra)}.")
            if "when" not in pairing or "suggest" not in pairing:
                raise SuggestionRuleError(f"{where}: precisa de 'when' e 'suggest'.")
            _check_conditions(pairing["when"], where=f"{where} (when)", allow_tag=False)
            _check_conditions(
                pairing.get("when_absent"), where=f"{where} (when_absent)",
                allow_tag=False, required=False,
            )
            _check_conditions(pairing["suggest"], where=f"{where} (suggest)", allow_tag=True)
            _check_weight(pairing.get("weight", 1), where=where)

        if "affinity_weight" in params:
            _check_weight(params["affinity_weight"], where="affinity_weight")

        distinct = params.get("distinct_from_cart") or []
        if not isinstance(distinct, list):
            raise SuggestionRuleError("'distinct_from_cart' precisa ser uma lista de atributos.")
        for ref in distinct:
            _check_attribute(ref, (), where=f"distinct_from_cart → '{ref}'")

        _check_conditions(
            params.get("one_per_cart") or None, where="one_per_cart",
            allow_tag=False, required=False,
        )

        price = params.get("price")
        if price is not None and price not in PRICE_POLICIES:
            raise SuggestionRuleError(
                f"'price' aceita: {', '.join(PRICE_POLICIES)} (ou nada)."
            )

        context = params.get("context") or {}
        if not isinstance(context, dict):
            raise SuggestionRuleError("'context' precisa ser um objeto.")
        for name, clause in context.items():
            where = f"context.{name}"
            if not isinstance(clause, dict):
                raise SuggestionRuleError(f"{where}: esperava um objeto.")
            extra = sorted(set(clause) - {"exclude"})
            if extra:
                raise SuggestionRuleError(f"{where}: só conheço 'exclude'.")
            if "exclude" in clause:
                _check_side(clause["exclude"], where=f"{where}.exclude", allow_tag=False)

        per_surface = params.get("per_surface") or {}
        if not isinstance(per_surface, dict):
            raise SuggestionRuleError("'per_surface' precisa ser um objeto.")
        for surface, limit in per_surface.items():
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
                raise SuggestionRuleError(
                    f"per_surface.{surface}: esperava um inteiro não negativo."
                )


class SubstituteRule(BaseRule):
    """``suggestion.substitute`` — o que oferecer no lugar do que faltou.

    O motor de substituto é da F2 (refino do Core no ``find_substitutes``); a
    regra existe desde a F1 para o gestor já cadastrar a política e para a
    validação recusar erro de digitação antes de ele importar.
    """

    code = SUBSTITUTE_REF
    label = "Sugestão de substituto"
    rule_type = "suggestion"

    KNOWN = frozenset({
        "must_match", "prefer", "approximate", "price_band", "cross_collection_when_empty",
    })

    def __init__(self, **params):
        self.params = dict(params)
        self.validate_params(self.params)

    @classmethod
    def validate_params(cls, params: dict) -> None:
        unknown = sorted(set(params) - cls.KNOWN)
        if unknown:
            raise SuggestionRuleError(
                f"Chave(s) que o esquema não conhece: {', '.join(unknown)}. "
                f"O esquema é: {', '.join(sorted(cls.KNOWN))}."
            )

        for key in ("must_match", "prefer", "approximate"):
            refs = params.get(key) or []
            if not isinstance(refs, list):
                raise SuggestionRuleError(f"'{key}' precisa ser uma lista.")
            for ref in refs:
                if key != "must_match" and ref in NON_ATTRIBUTE_SIGNALS:
                    continue
                _check_attribute(ref, (), where=f"{key} → '{ref}'")

        band = params.get("price_band")
        if band is not None:
            if isinstance(band, bool) or not isinstance(band, (int, float)):
                raise SuggestionRuleError("'price_band' é um número (0.30 = ±30%).")
            if not (0 < band <= 1):
                raise SuggestionRuleError("'price_band' fica entre 0 e 1.")

        cross = params.get("cross_collection_when_empty")
        if cross is not None and not isinstance(cross, bool):
            raise SuggestionRuleError("'cross_collection_when_empty' é verdadeiro ou falso.")


def _check_weight(weight, *, where: str) -> None:
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        raise SuggestionRuleError(f"{where}: o peso é um número.")
    if weight < 0:
        raise SuggestionRuleError(f"{where}: o peso não pode ser negativo.")
