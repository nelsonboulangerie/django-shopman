"""Terminal — o aparelho onde a gaveta está.

Config, não dinheiro (ADR-011: "terminal não guarda dinheiro"). O que a loja
decide sobre o balcão mora aqui: canal, local, hardware em ``metadata``. Quem
guarda dinheiro é o turno, e quem conta o dinheiro é o livro.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def _default_channel_ref() -> str:
    return str(getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "pdv"))


class Terminal(models.Model):
    ref = models.SlugField(_("ref"), max_length=80, unique=True)
    label = models.CharField(_("rótulo"), max_length=120, blank=True, default="")
    channel_ref = models.CharField(_("canal"), max_length=80, default=_default_channel_ref)
    location_ref = models.CharField(_("local"), max_length=120, blank=True, default="")
    is_active = models.BooleanField(_("ativo"), default=True)
    metadata = models.JSONField(
        _("metadados"),
        default=dict,
        blank=True,
        help_text=_("Configuração do aparelho (hardware, trava). Schema em docs/reference/data-schemas.md."),
    )
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        app_label = "cashman"
        ordering = ["ref"]
        verbose_name = _("terminal")
        verbose_name_plural = _("terminais")

    def __str__(self) -> str:
        return self.label or self.ref

    @classmethod
    def default(cls) -> Terminal:
        """O terminal que existe quando ninguém configurou nenhum.

        Uma loja com um só balcão não deve precisar cadastrar terminal para
        abrir o caixa; mas o turno precisa de um, porque a custódia é sempre de
        uma gaveta física.
        """
        terminal, _created = cls.objects.get_or_create(
            ref="pdv-main",
            defaults={"label": "PDV principal", "channel_ref": _default_channel_ref(), "is_active": True},
        )
        return terminal
