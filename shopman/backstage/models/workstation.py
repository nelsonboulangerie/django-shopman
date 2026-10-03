"""Posto de trabalho: ONDE o dispositivo fica, separado de ONDE a gaveta está.

Até 03/10/2026 o posto era o ``cashman.Terminal``: a estação confiável guardava o
``Terminal.ref`` no cookie, e a lista de postos era a lista de caixas. Isso misturava
duas coisas. O tablet da Expedição, a estação de Lanches e a Sala Forno são postos e
não têm gaveta; tratá-los como caixa ou deixava o posto sem nome, ou dava a eles um
turno que não existe.

Agora o posto é este modelo, e o caixa é um TIPO de posto:

* ``kind == cash_desk`` → amarrado a um ``Terminal`` (gaveta e turno). Todo
  ``Terminal`` tem o seu posto, criado junto com ele (``services.workstations``).
* qualquer outro tipo → sem ``Terminal``. Posto sem caixa NUNCA abre gaveta nem turno:
  as mutações de dinheiro do PDV exigem que o ref da estação seja um ``Terminal``
  ativo, e o ref de um posto sem caixa nunca é (``clean`` recusa a colisão).

**O cookie não mudou.** A confiança de dispositivo (``doorman.TrustedDevice``) guarda
``subject_id = Workstation.ref``. Para o posto de um caixa, esse ref é o próprio
``Terminal.ref``: os dispositivos já provisionados continuam reconhecidos sem
ninguém refazer nada.

As preferências do posto (a arrumação das colunas do Gestor, ``gestor_board``) moram
em ``metadata``; o inventário de chaves está em ``docs/reference/data-schemas.md``.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from shopman.backstage.workstation_vocabulary import CASH_DESK, KIND_LABELS, kind_label


class Workstation(models.Model):
    ref = models.SlugField("ref", max_length=80, unique=True)
    label = models.CharField("nome", max_length=80)
    # Sem ``choices`` de propósito: o rótulo do tipo mora em
    # ``workstation_vocabulary.KIND_LABELS`` e renomear não pode virar migração.
    kind = models.CharField("tipo", max_length=32)
    terminal = models.OneToOneField(
        "cashman.Terminal",
        verbose_name="caixa",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="workstation",
        help_text="Só o posto Caixa tem gaveta e turno.",
    )
    metadata = models.JSONField(
        "preferências",
        default=dict,
        blank=True,
        help_text="Preferências do posto (ex.: gestor_board). Schema em docs/reference/data-schemas.md.",
    )
    is_active = models.BooleanField("ativo", default=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        app_label = "backstage"
        ordering = ["label", "ref"]
        verbose_name = "posto de trabalho"
        verbose_name_plural = "postos de trabalho"

    def __str__(self) -> str:
        return self.label or self.ref

    @property
    def kind_label(self) -> str:
        return kind_label(self.kind)

    @property
    def has_cash_desk(self) -> bool:
        return self.terminal_id is not None

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.kind not in KIND_LABELS:
            errors["kind"] = "Tipo de posto desconhecido."
        if self.kind == CASH_DESK and self.terminal_id is None:
            errors["terminal"] = "O posto Caixa precisa de um caixa (terminal)."
        if self.terminal_id is not None and self.terminal.ref != self.ref:
            # O cookie do dispositivo guarda o ref do posto, e o PDV procura a gaveta
            # por esse mesmo ref. Divergir seria um posto de caixa sem gaveta.
            errors["ref"] = "O posto de um caixa usa o mesmo ref do caixa."
        if self.terminal_id is None and self.ref:
            from shopman.cashman.models import Terminal

            if Terminal.objects.filter(ref=self.ref).exists():
                # O ref de um posto sem caixa nunca pode ser o de um Terminal: o
                # dispositivo dele passaria a abrir aquela gaveta.
                errors["ref"] = "Já existe um caixa com este ref."
        if errors:
            raise ValidationError(errors)
