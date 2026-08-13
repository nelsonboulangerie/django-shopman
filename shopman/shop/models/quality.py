"""Catálogos de qualidade da fornada — a POLÍTICA mora no framework (ADR-017).

O core do craftsman carrega ponteiros opacos (``WorkOrderItem.quality_grade_ref``
e ``quality_defect_ref``); quem dá significado a eles é o deployment, nestes dois
catálogos editáveis no Admin. O core nunca interpreta: não sabe que ``minimal``
vale menos que ``standard`` nem que ``contaminated`` obriga descarte.

Regra do eixo único (QC-FORNADA §2/§3): **quem define preço é só o grau** —
acrescentar um defeito novo nunca exige uma decisão de precificação. O veto
(``forces_discard``) é só para o que torna o alimento inseguro, nunca para o que
o torna feio: defeito cosmético vende com desconto.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class QualityGrade(models.Model):
    """Um degrau da escala de qualidade — nomeia uma faixa, não um pão.

    ``rank`` é a hierarquia (maior = melhor) e substitui o literal triplicado
    ``QUALITY_LEVELS``/``QUALITY_CHOICES``. ``markdown_percent`` é resolvido UMA
    vez, no finish, e congela no lote (``Batch.nonconformity_percent``): mudar a
    tabela amanhã não reescreve os lotes de ontem.
    """

    ref = models.CharField(
        _("código"),
        max_length=32,
        unique=True,
        help_text=_("excellent | standard | fair | minimal — fixo, o rótulo é que edita"),
    )
    label = models.CharField(_("rótulo"), max_length=50)
    rank = models.IntegerField(
        _("hierarquia"),
        unique=True,
        help_text=_("Maior = melhor. A ordem tem que ser óbvia num relance."),
    )
    markdown_percent = models.PositiveSmallIntegerField(
        _("desconto (%)"),
        default=0,
        help_text=_("Resolvido no fechamento da fornada e congelado no lote."),
    )
    is_default = models.BooleanField(
        _("padrão"),
        default=False,
        help_text=_("O grau pré-selecionado ao fechar a fornada."),
    )

    class Meta:
        verbose_name = _("grau de qualidade")
        verbose_name_plural = _("graus de qualidade")
        ordering = ("-rank",)
        constraints = [
            # Unique parcial: no máximo UM grau padrão.
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True),
                name="quality_grade_single_default",
            ),
            # O percentual congela no lote (Batch.nonconformity_percent);
            # acima de 100 escreveria preço negativo na venda.
            models.CheckConstraint(
                condition=models.Q(markdown_percent__lte=100),
                name="quality_grade_markdown_at_most_100",
            ),
        ]

    def __str__(self) -> str:
        return self.label


class QualityDefect(models.Model):
    """Um tipo nomeado de falha — a CAUSA, não o sintoma.

    "Pequeno" não ensina nada num relatório; a causa quase sempre é fermentação,
    que pode ter faltado ou sobrado. O ``hint`` devolve o sintoma ao operador
    ("pequeno, denso, rasgou") para a inferência não custar nada às 5h da manhã.

    Nenhum defeito carrega severidade: "escuro" e "queimado" são ``overbaked``
    em graus diferentes. A palavra não muda quando a severidade muda.
    """

    ref = models.CharField(_("código"), max_length=32, unique=True)
    label = models.CharField(_("rótulo"), max_length=50)
    hint = models.CharField(
        _("dica"),
        max_length=100,
        blank=True,
        help_text=_("O sintoma que o padeiro vê — segunda linha do botão."),
    )
    forces_discard = models.BooleanField(
        _("obriga descarte"),
        default=False,
        help_text=_(
            "SÓ segurança alimentar (matéria estranha). Defeito cosmético nunca "
            "veta: vende com desconto."
        ),
    )
    position = models.IntegerField(_("ordem"), default=0)
    is_active = models.BooleanField(_("ativo"), default=True)

    class Meta:
        verbose_name = _("defeito de fornada")
        verbose_name_plural = _("defeitos de fornada")
        ordering = ("position", "ref")

    def clean(self) -> None:
        # Desativar o defeito vetado tiraria "Contaminado" do quiosque e o
        # operador registraria contaminação como defeito comum — lote com
        # desconto de comida insegura. Primeiro tire o veto, conscientemente.
        if not self.is_active and self.forces_discard:
            raise ValidationError(
                {
                    "is_active": _(
                        "Defeito com descarte obrigatório não pode ser desativado. "
                        "Remova o veto primeiro, se for intencional."
                    )
                }
            )

    def __str__(self) -> str:
        return self.label
