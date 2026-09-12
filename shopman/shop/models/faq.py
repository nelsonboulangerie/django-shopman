"""Public frequently asked questions shared by every customer surface."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models
from django.utils.text import slugify
from simple_history.models import HistoricalRecords


class FAQEntry(models.Model):
    """A curated public answer, independent from any delivery provider."""

    RESERVED_OPERATIONAL_QUESTIONS = {
        "voces-fazem-entrega",
        "quais-sao-os-horarios-de-funcionamento",
        "onde-voces-ficam",
        "como-falar-com-voces",
    }

    ref = models.SlugField(
        "referência",
        max_length=96,
        unique=True,
        blank=True,
        help_text="Identificador estável gerado da pergunta no primeiro salvamento.",
    )
    question = models.CharField("pergunta", max_length=220)
    answer = models.TextField(
        "resposta",
        validators=[MaxLengthValidator(2000)],
        help_text="Até 2.000 caracteres. Não repita preço, estoque, taxa, cobertura ou horário operacional.",
    )
    search_terms = models.CharField(
        "termos de busca",
        max_length=300,
        blank=True,
        help_text="Sinônimos separados por vírgula usados pela busca da Concierge.",
    )
    position = models.PositiveSmallIntegerField(
        "posição",
        default=0,
        help_text="Menor número aparece primeiro.",
    )
    is_published = models.BooleanField(
        "publicada",
        default=False,
        help_text="Publica a resposta no site e permite que a Concierge a use.",
    )
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "pergunta frequente"
        verbose_name_plural = "perguntas frequentes"
        ordering = ("position", "id")
        indexes = [models.Index(fields=("is_published", "position"))]

    def __str__(self) -> str:
        return self.question

    def clean(self):
        super().clean()
        self._validate_operational_question()

    def _validate_operational_question(self):
        if self.is_published and slugify(self.question) in self.RESERVED_OPERATIONAL_QUESTIONS:
            raise ValidationError(
                {
                    "question": (
                        "Esta resposta é operacional e já vem da configuração canônica da loja. "
                        "Edite entrega, horários, endereço ou contato na seção correspondente."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self._validate_operational_question()
        if not self.ref:
            base = slugify(self.question)[:80] or "pergunta"
            candidate = base
            suffix = 2
            while type(self).objects.exclude(pk=self.pk).filter(ref=candidate).exists():
                candidate = f"{base[: max(1, 91 - len(str(suffix)))]}-{suffix}"
                suffix += 1
            self.ref = candidate
        return super().save(*args, **kwargs)
