"""Margem de segurança do rendimento das massas.

A balança da bancada tem divisão finita — na casa, 2 g. Com a régua "nunca
abaixo do alvo" (o peso anunciado ao cliente é PISO, bloco D do
``WP-FICHA-DE-PRODUTO-E-PROMESSA``), o padeiro para de tirar massa quando o
mostrador chega ao alvo, então cada peça sai no intervalo ``[W, W + d)``. E aí
está a primeira armadilha: o excesso **esperado** por peça é ``d/2``, não ``d``.

Supor ``d`` parece prudência e é desperdício medido: pâton de 60 g em balança
de 2 g, 100 peças por fornada — ``100 × 2 g = 200 g`` contra ``100 × 1 g =
100 g``. **100 g de massa jogados fora, toda fornada**, por um número que
ninguém revisita.

A segunda armadilha é achar que uma porcentagem única resolve. **São duas
perdas com formas diferentes**, e nenhuma porcentagem acerta as duas ao mesmo
tempo::

    massa a fazer = N × peso da peça
                  + N × d/2                 arredondamento: escala com o NÚMERO de peças
                  + perda da masseira       filme na bacia: ~fixa por fornada
                  + colchão ≈ 3·d·√(N/12)   variância, que ENCOLHE em proporção

O arredondamento cresce com N; a perda da masseira não cresce (é o mesmo filme
de massa na bacia, faça-se 20 ou 200 peças). Uma porcentagem que acerte a
fornada pequena sobra na grande, e vice-versa.

**A peça isolada é incerta; a fornada não é.** Cada arredondamento é uma
variável uniforme em ``[0, d)``: média ``d/2`` e desvio ``d/√12``. A soma de N
delas tem desvio ``d·√(N/12)`` — em 25 peças com ``d = 2 g``, cerca de 2,9 g,
que é ruído perto dos 25 g do arredondamento médio. Por isso a margem se orça
**na fornada**, nunca por peça: por peça o erro relativo é enorme; somado, ele
se dilui. O colchão de três desvios existe para cobrir a cauda, e é ele que
**encolhe em proporção** quando N cresce (``√N`` contra ``N``).

E o que sobrar não é perda: **é massa velha de amanhã**, que a casa já modela
como teto (``old_dough`` / ``cap_pct``). O alvo desta conta não é sobra zero —
é sobra que caiba no teto do dia seguinte.

⚠️ **A perda da masseira não se chuta para sempre.** Nesta rodada ela é
declarada por ficha (``Recipe.meta["mixer_loss_g"]``) com padrão conservador. O
passo seguinte é o sistema APRENDER a perda real: o ledger já sabe o que foi
consumido (perna de insumos do ``production_changed``) e o que foi produzido
(perna de saída), e a diferença entre a massa dos insumos e a massa rendida é
exatamente a perda que aqui está declarada. Ver a nota de aprendizado no plano.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation

from shopman.utils import units

_TWO = Decimal("2")
_TWELVE = Decimal("12")


@dataclass(frozen=True)
class YieldMargin:
    """As três parcelas da margem, separadas — porque têm formas diferentes.

    Guardá-las somadas esconderia justamente o que a tela precisa dizer: de
    onde vieram os gramas a mais. Todas as quantidades estão em ``unit``.
    """

    #: Número de peças da fornada (N). É ele que escala o arredondamento.
    pieces: Decimal
    #: Unidade em que a margem é expressa — a mesma do insumo na ficha.
    unit: str
    #: Divisão da balança (d), já convertida para ``unit``.
    scale_precision: Decimal
    #: ``N × d/2`` — o excesso ESPERADO, não o pior caso.
    rounding: Decimal
    #: Filme de massa que fica na bacia. ~Fixa por fornada, não por peça.
    mixer_loss: Decimal
    #: ``k · d · √(N/12)`` — colchão de variância, k desvios-padrão.
    variance: Decimal

    @property
    def total(self) -> Decimal:
        return self.rounding + self.mixer_loss + self.variance

    def reason(self) -> str:
        """Motivo em uma linha, para a tela. Sem isso é número que cresceu sozinho."""
        pieces = _plain(self.pieces)
        return (
            f"margem: {pieces} peças × meia divisão da balança "
            f"({_plain(self.rounding)} {self.unit}) "
            f"+ perda da masseira ({_plain(self.mixer_loss)} {self.unit}) "
            f"+ folga de variação ({_plain(self.variance)} {self.unit})"
        )


@dataclass(frozen=True)
class ScaleTarget:
    """Alvo operacional de uma pesagem numa balança de divisão finita.

    ``theoretical_g`` preserva a conta da ficha. ``target_g`` é o número que o
    operador deve enxergar: o primeiro múltiplo da divisão da balança que não
    fica abaixo daquela conta. A faixa aceita fica registrada para a futura
    captura da balança, mas não transforma a ficha numa sessão de pesagem.
    """

    theoretical_g: Decimal
    precision_g: Decimal
    target_g: Decimal
    accepted_min_g: Decimal
    accepted_max_g: Decimal

    @property
    def rounding_delta_g(self) -> Decimal:
        return self.target_g - self.theoretical_g


def compute_scale_target(quantity_g, *, scale_precision=None) -> ScaleTarget:
    """Arredonda uma quantidade em gramas para cima segundo a balança.

    A precisão vem da mesma configuração que já governa a margem de rendimento
    (``CRAFTSMAN["SCALE_PRECISION_G"]``). Assim planejamento e etiqueta não
    podem contar histórias diferentes sobre o mesmo equipamento.

    Com a balança padrão de 2 g, 101 g vira 102 g e 102 g permanece 102 g.
    Nunca se arredonda para baixo. Quantidade ou precisão inválida falham cedo:
    um alvo silenciosamente incorreto no chão de fábrica é pior que não emitir
    a etiqueta.
    """

    theoretical_g = _decimal(quantity_g)
    precision_g = _decimal(scale_precision) if scale_precision is not None else scale_precision_g()
    if not theoretical_g.is_finite() or theoretical_g < 0:
        raise ValueError("quantity_g deve ser um decimal finito e >= 0")
    if not precision_g.is_finite() or precision_g <= 0:
        raise ValueError("scale_precision deve ser um decimal finito e > 0")

    steps = (theoretical_g / precision_g).to_integral_value(rounding=ROUND_CEILING)
    target_g = steps * precision_g
    return ScaleTarget(
        theoretical_g=theoretical_g,
        precision_g=precision_g,
        target_g=target_g,
        accepted_min_g=target_g,
        accepted_max_g=target_g + precision_g,
    )


def scale_precision_g() -> Decimal:
    """Divisão da balança de bancada, em gramas.

    É propriedade do EQUIPAMENTO, não da receita: uma balança serve todas as
    fichas. Por isso mora no ``conf`` do pacote (``SCALE_PRECISION_G``), e não
    em ``Recipe.meta``. Trocar a balança é uma linha de settings.
    """
    from shopman.craftsman.conf import get_setting

    return _decimal(get_setting("SCALE_PRECISION_G"))


def yield_margin_sigmas() -> Decimal:
    """Quantos desvios-padrão de colchão. Padrão 3 (cauda praticamente coberta)."""
    from shopman.craftsman.conf import get_setting

    return _decimal(get_setting("YIELD_MARGIN_SIGMAS"))


def mixer_loss_g_for(recipe) -> Decimal:
    """Perda da masseira DESTA ficha, em gramas.

    Declarada em ``Recipe.meta["mixer_loss_g"]``; sem declaração, cai no padrão
    conservador de ``MIXER_LOSS_G``. O padrão é **estimativa não auditada** —
    ele existe para a conta não parar, não para virar verdade. Ver a nota de
    aprendizado no topo do módulo.
    """
    from shopman.craftsman.conf import get_setting

    declared = (getattr(recipe, "meta", None) or {}).get("mixer_loss_g") if recipe else None
    if declared is None:
        return _decimal(get_setting("MIXER_LOSS_G"))
    try:
        value = _decimal(declared)
    except (InvalidOperation, TypeError, ValueError):
        # Lixo no JSONField não vira zero silencioso: cai no padrão da casa, que
        # é o número conservador, e não no "não sei" que faria massa de menos.
        return _decimal(get_setting("MIXER_LOSS_G"))
    return value if value >= 0 else _decimal(get_setting("MIXER_LOSS_G"))


def compute_yield_margin(
    *,
    pieces,
    unit: str,
    mixer_loss_g=None,
    scale_precision=None,
    sigmas=None,
) -> YieldMargin | None:
    """Orça a margem de UMA fornada de N peças, na unidade do insumo.

    Devolve ``None`` quando não há o que orçar (nenhuma peça) ou quando a
    unidade não é de massa — margem de rendimento é conversa de massa, e
    adivinhar a dimensão seria o oposto da ADR-024 §R4.

    ``pieces`` é o TOTAL de peças que saem desta massa no dia, somando as work
    orders que a compartilham: duas ordens (baguete e bâtard) da mesma Massa
    Tradição são UMA mistura na masseira, então a perda da masseira entra uma
    vez só e o colchão de variância é o da soma, não a soma dos colchões.
    """
    pieces = _decimal(pieces)
    if pieces <= 0:
        return None
    if units.dimension(unit) != units.MASS:
        return None

    precision_g = _decimal(scale_precision) if scale_precision is not None else scale_precision_g()
    loss_g = _decimal(mixer_loss_g) if mixer_loss_g is not None else _decimal(0)
    k = _decimal(sigmas) if sigmas is not None else yield_margin_sigmas()

    d = units.convert(precision_g, "g", unit)
    loss = units.convert(loss_g, "g", unit)

    # Excesso ESPERADO por peça é meia divisão. Ver o desperdício medido no
    # topo do módulo: supor a divisão inteira joga fora d/2 por peça.
    rounding = pieces * d / _TWO
    # Desvio da SOMA de N uniformes [0, d): d·√(N/12). Cresce com √N, então o
    # colchão encolhe em proporção conforme a fornada aumenta.
    variance = k * d * (pieces / _TWELVE).sqrt()

    return YieldMargin(
        pieces=pieces,
        unit=unit,
        scale_precision=d,
        rounding=rounding,
        mixer_loss=loss,
        variance=variance,
    )


def _decimal(value) -> Decimal:
    """Decimal sempre — float não entra em conta de massa (ADR-002 em espírito)."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _plain(value: Decimal) -> str:
    """Número legível na tela: até 3 casas, sem zeros à toa, vírgula decimal."""
    quantized = value.quantize(Decimal("0.001")).normalize()
    if quantized == quantized.to_integral_value():
        quantized = quantized.quantize(Decimal("1"))
    return format(quantized, "f").replace(".", ",")
