"""O documento fiscal emitido: o registro de autoridade da nota (D-037, #3428).

Até 23/11/2026 a nota existia só como chaves ``nfce_*`` num JSON do pedido,
que outros fluxos também escrevem. Decisão do dono (D-037, 10/11/2026): o
documento ganha tabela própria ANTES da primeira NFC-e real, porque depois da
tag ``go-live-v1`` mudar o lugar da nota seria backfill de nota fiscal real.

A linha nasce ``pending`` e é gravada ANTES do pedido ao provedor. Assim uma
interrupção entre a autorização na SEFAZ e a gravação local deixa um rastro:
quem retoma acha a linha pendente, consulta o provedor pela mesma referência e
completa o MESMO documento, em vez de emitir outro.

O fiscalman não conhece o pedido (os Cores não se importam): ``reference`` é a
referência que o chamador usa no provedor, e no orquestrador ela é o
``Order.ref``. Escrita só por :mod:`shopman.fiscalman.services`.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class FiscalDocument(models.Model):
    class Kind(models.TextChoices):
        NFCE = "nfce", _("NFC-e")

    class Status(models.TextChoices):
        # Gravado antes do pedido ao provedor: a nota pode ou não existir lá. Só
        # sai daqui com a nota confirmada pelo provedor: recusa, erro e resposta
        # perdida deixam a linha pendente, e quem retoma consulta antes de emitir.
        PENDING = "pending", _("Aguardando o provedor")
        AUTHORIZED = "authorized", _("Autorizada")
        CANCELLED = "cancelled", _("Cancelada")

    kind = models.CharField(_("tipo"), max_length=16, choices=Kind.choices, default=Kind.NFCE)
    reference = models.CharField(_("referência no provedor"), max_length=64)
    status = models.CharField(_("situação"), max_length=16, choices=Status.choices, default=Status.PENDING)

    access_key = models.CharField(_("chave de acesso"), max_length=44, blank=True, default="")
    number = models.PositiveIntegerField(_("número"), null=True, blank=True)
    series = models.PositiveIntegerField(_("série"), null=True, blank=True)
    protocol_number = models.CharField(_("protocolo de autorização"), max_length=32, blank=True, default="")
    # A Autorização de Uso na SEFAZ, de onde conta o prazo de cancelamento
    # (RICMS/PR, Anexo III, Subanexo I, art. 35). Nulo quando o provedor não disse.
    authorized_at = models.DateTimeField(_("autorizada em"), null=True, blank=True)
    xml_url = models.URLField(_("XML"), max_length=500, blank=True, default="")
    danfe_url = models.URLField(_("DANFE"), max_length=500, blank=True, default="")
    qrcode_url = models.URLField(_("consulta (QR code)"), max_length=500, blank=True, default="")

    cancellation_protocol = models.CharField(_("protocolo de cancelamento"), max_length=32, blank=True, default="")
    cancelled_at = models.DateTimeField(_("cancelada em"), null=True, blank=True)

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("documento fiscal")
        verbose_name_plural = _("documentos fiscais")
        constraints = [
            # Uma referência é um documento: o provedor recusa reusar a referência
            # de nota autorizada, e o retry tem de achar a MESMA linha.
            models.UniqueConstraint(fields=["kind", "reference"], name="fiscalman_document_unique_reference"),
            models.UniqueConstraint(
                fields=["access_key"], condition=~Q(access_key=""), name="fiscalman_document_unique_access_key",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.reference} ({self.status})"
