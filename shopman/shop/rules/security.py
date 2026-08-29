"""Regra de DESTAQUE da trilha de acesso — o que o olho do gerente deve pegar.

⚠️ **Esta regra não suprime nada.** Todo login vira aviso para o dono da conta,
sempre; o que ela decide é qual deles chega **destacado** na lista. A distinção é
o ponto todo do desenho (decisão do dono, 29/08/2026): errar o critério passa a
custar "não destacou" em vez de "não avisou", e um falso negativo que ainda
aparece na lista é recuperável — um que nunca chegou, não.

Também não participa de nenhum estágio do engine: ``rule_type`` é ``"config"``, e
nenhum ``get_active_rules(stage=…)`` pede esse estágio. Ela existe como classe
porque ``RuleConfig.rule_path`` só aceita subclasse de ``BaseRule`` sob os
prefixos autorizados — é o jeito da casa de ter parâmetro editável no Admin sem
inventar um segundo lugar para guardar configuração.

Sem linha de ``RuleConfig``, valem os defaults do ``__init__``: a feature funciona
configurada em zero lugares.
"""

from __future__ import annotations

import logging

from shopman.shop.rules import BaseRule

logger = logging.getLogger(__name__)


class SignInHighlightRule(BaseRule):
    """Quais acessos de operador chegam destacados na caixa da pessoa.

    Os parâmetros são argumentos do ``__init__`` **de propósito**: é assim que o
    ``engine.load_rule`` descobre, por introspecção da assinatura, que uma chave
    escrita errada no Admin não existe — e recusa carregar a regra inteira, como
    manda a casa. Guardar os mesmos nomes num dicionário à parte criaria uma
    segunda lista para desincronizar da primeira, e a validação passaria a
    depender de alguém lembrar de atualizar as duas.
    """

    code = "sign_in_highlight"
    label = "Destaque de acessos de operador"
    #: Não é `validator` nem `modifier`: nenhum estágio do engine a consome, e
    #: `register_active_rules` a ignora. Ela existe como classe porque é assim
    #: que a casa guarda parâmetro editável no Admin.
    rule_type = "config"

    def __init__(
        self,
        *,
        # Crachá é posse pura: sem segundo fator, e se perde no chão. É o sinal
        # que motivou o pedido inteiro.
        badge: bool = True,
        # Credencial certa, lugar errado — a assinatura do uso indevido.
        unknown_station: bool = True,
        # 3h da manhã não tem operação legítima.
        outside_hours: bool = True,
        # Crachá passando de mão em mão.
        burst_count: int = 4,
        burst_minutes: int = 10,
        # Tentativa e acerto.
        after_failure: bool = True,
        # Qualquer recusa se destaca sozinha: é o sinal mais barato que existe.
        failure: bool = True,
    ):
        self.badge = badge
        self.unknown_station = unknown_station
        self.outside_hours = outside_hours
        self.burst_count = burst_count
        self.burst_minutes = burst_minutes
        self.after_failure = after_failure
        self.failure = failure

    def as_params(self) -> dict:
        return {
            "badge": self.badge,
            "unknown_station": self.unknown_station,
            "outside_hours": self.outside_hours,
            "burst_count": self.burst_count,
            "burst_minutes": self.burst_minutes,
            "after_failure": self.after_failure,
            "failure": self.failure,
        }


def params_or_defaults() -> dict:
    """Os parâmetros configurados, ou os defaults — nunca uma mistura dos dois.

    Quem valida é o ``load_rule`` do engine, pela assinatura do ``__init__``:
    chave desconhecida levanta e a regra **não carrega**, que é a regra da casa
    e vale para toda `RuleConfig`, não só para esta.

    O que decidimos aqui é o que fazer com o "não carrega": cair nos
    **defaults**, alto e claro no log, e não desligar o destaque. Esta regra só
    governa REALCE, então uma configuração quebrada virando "parou de sinalizar
    anomalia em silêncio" seria exatamente a falha que o trabalho existe para
    evitar. Os defaults são o piso seguro; a configuração quebrada é a ignorada.
    """
    from shopman.shop.models import RuleConfig
    from shopman.shop.rules.engine import load_rule

    # Sem try aqui de propósito: quem chama (``detect_anomalies``) já embrulha e
    # loga, e um segundo catch mudo neste caminho engoliria um banco fora sem
    # deixar rastro — que é exatamente o que o gate de higiene de exceção proíbe.
    config = RuleConfig.objects.filter(ref=SignInHighlightRule.code, enabled=True).first()

    if config is None:
        return SignInHighlightRule().as_params()

    try:
        return load_rule(config).as_params()
    except Exception:
        logger.error(
            "sign_in_highlight: configuração NÃO carrega, valendo os defaults. "
            "Parâmetros aceitos: %s",
            sorted(SignInHighlightRule().as_params()),
            exc_info=True,
        )
        return SignInHighlightRule().as_params()
