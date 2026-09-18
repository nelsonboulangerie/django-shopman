"""Etiquetas de timer da bancada — o disparo de UM toque no fournil.

A página ``/timers`` do app de Produção existe para lembrar o padeiro de algo
que ele já sabe fazer: a estufa, o freezer, o descanso da massa, a pausa do
café. O que custava caro não era o timer — era DIGITAR os minutos e o nome com
a mão suja, às cinco da manhã. A etiqueta resolve isso: um toque no nome
dispara o tempo padrão dela, sem teclado e sem confirmação.

Duas origens, uma lista só. O gestor cadastra no Admin o que é rotina da casa;
o operador cria na hora o que a rotina não previu, e a etiqueta nasce ativa
para todo mundo — não é rascunho dele. ``origin`` guarda quem a criou para o
gestor poder CURAR depois (renomear, ajustar o tempo, desativar) sem precisar
adivinhar o que era política e o que era invenção do turno.

**Dois nomes iguais não podem coexistir ativos.** "Pausa-café", "pausa cafe" e
"PAUSA CAFÉ" são a mesma coisa para quem olha a tela, e três chips repetidos
transformam o disparo de um toque numa escolha. Por isso o rótulo tem um gêmeo
comparável (``normalized_label``) e uma unique parcial sobre as ativas: a
criação pelo operador devolve a etiqueta existente em vez de criar a irmã, e o
Admin recusa a duplicata na cara do gestor. Desativar libera o nome — o
histórico não depende destas linhas, porque o timer vive no dispositivo.
"""

from __future__ import annotations

import re
import unicodedata

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify

#: Teto de minutos. O numpad da tela já recusa quatro dígitos; aqui a regra
#: existe para o Admin e para a API dizerem o mesmo que a tela diz.
MAX_TIMER_MINUTES = 999


def normalize_tag_label(label: str) -> str:
    """Nome comparável: sem acento, sem pontuação, sem espaço sobrando, minúsculo.

    Espelho exato de ``normalizeTagLabel`` em
    ``surfaces/production-nuxt/app/presentation/timers.ts``. Quem decide é este
    lado; a tela usa o gêmeo só para avisar antes de gravar.
    """
    decomposed = unicodedata.normalize("NFD", str(label or ""))
    without_accents = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"[^0-9A-Za-z]+", " ", without_accents).strip().lower()


class TimerTagOrigin(models.TextChoices):
    ADMIN = "admin", "Cadastrada pelo gestor"
    OPERATOR = "operator", "Criada no fournil"


class TimerTagManager(models.Manager):
    def active(self):
        return self.filter(is_active=True)

    def create_from_operator(self, *, label: str, minutes: int) -> tuple[TimerTag, bool]:
        """A etiqueta que o operador acabou de nomear — ou a que já existia.

        Devolve ``(tag, criada)``. Quando há equivalente ativa, ela volta
        INTACTA: o tempo digitado agora não reescreve o tempo padrão que a casa
        já combinou, senão cada turno redefiniria em silêncio o que "Estufa"
        significa. O timer daquele toque usa o que o operador digitou; a
        etiqueta segue como está.
        """
        normalized = normalize_tag_label(label)
        existing = self.active().filter(normalized_label=normalized).first()
        if existing is not None:
            return existing, False
        tag = self.model(
            ref=unique_tag_ref(label),
            label=str(label).strip(),
            minutes=minutes,
            origin=TimerTagOrigin.OPERATOR,
            position=_next_position(self),
        )
        tag.save()
        return tag, True


def _next_position(manager) -> int:
    """No fim da fileira: a etiqueta nova não empurra o que o gestor ordenou."""
    last = manager.aggregate(models.Max("position")).get("position__max")
    return (last or 0) + 10


def unique_tag_ref(label: str) -> str:
    """Slug estável a partir do rótulo, com sufixo só quando já existe."""
    base = slugify(label)[:40] or "etiqueta"
    candidate = base
    suffix = 2
    while TimerTag.objects.filter(ref=candidate).exists():
        candidate = f"{base[:40 - len(str(suffix)) - 1]}-{suffix}"
        suffix += 1
    return candidate


class TimerTag(models.Model):
    """Um disparo nomeado de timer: um rótulo e o tempo que ele significa."""

    ref = models.SlugField("ref", max_length=48, unique=True)
    label = models.CharField(
        "rótulo",
        max_length=40,
        help_text="O que o padeiro lê no chip. Curto: cabe num toque de olho.",
    )
    normalized_label = models.CharField(
        "rótulo comparável",
        max_length=40,
        editable=False,
        help_text="Derivado do rótulo. Existe para impedir duas etiquetas com o mesmo nome.",
    )
    minutes = models.PositiveSmallIntegerField(
        "duração (min)",
        validators=[MinValueValidator(1), MaxValueValidator(MAX_TIMER_MINUTES)],
        help_text="O tempo que um toque no chip dispara. O operador ainda pode somar depois.",
    )
    origin = models.CharField(
        "origem",
        max_length=16,
        choices=TimerTagOrigin.choices,
        default=TimerTagOrigin.ADMIN,
        help_text="O que veio do fournil é o que vale a pena revisar aqui.",
    )
    position = models.PositiveSmallIntegerField(
        "ordem",
        default=0,
        help_text="Menor primeiro. O que a casa dispara todo dia fica no começo da fileira.",
    )
    is_active = models.BooleanField(
        "ativa",
        default=True,
        help_text="Etiqueta inativa some da tela do fournil e libera o nome.",
    )
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    objects = TimerTagManager()

    class Meta:
        verbose_name = "etiqueta de timer"
        verbose_name_plural = "etiquetas de timer"
        ordering = ["position", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["normalized_label"],
                condition=models.Q(is_active=True),
                name="timer_tag_unique_active_label",
                violation_error_message=(
                    "Já existe uma etiqueta ativa com este nome. Edite a que existe "
                    "ou desative-a antes de criar outra."
                ),
            ),
        ]

    def __str__(self) -> str:
        return self.label

    def clean(self) -> None:
        # Antes de ``validate_constraints`` (que roda depois do ``clean`` no
        # ``full_clean``): sem isto o Admin compararia o gêmeo antigo e deixaria
        # passar a duplicata que o banco recusaria depois, com erro de servidor.
        self.normalized_label = normalize_tag_label(self.label)

    def save(self, *args, **kwargs) -> None:
        self.normalized_label = normalize_tag_label(self.label)
        # ``update_or_create`` (o caminho do seed) salva com ``update_fields``
        # desde o Django 4.2. Sem carregar o gêmeo junto, o rótulo mudaria e a
        # comparação continuaria valendo o nome antigo — a unique parcial
        # deixaria passar exatamente a duplicata que ela existe para impedir.
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "label" in set(update_fields):
            kwargs["update_fields"] = {*update_fields, "normalized_label"}
        super().save(*args, **kwargs)
