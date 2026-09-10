"""O rastro do contato LIBERADO pelo balcão — o que era, de quem saiu, quem soltou.

Liberar um contato preso num cadastro desativado apaga o ``ContactPoint`` (ou o
``CustomerIdentifier``) para que o UNIQUE global pare de recusar a venda. É a
saída certa e ela precisa existir. O que faltava era o RASTRO: um ``.delete()``
não tem desfazer, e a única memória do que havia ali era uma linha de log — que
ninguém lê e que não reconstrói cadastro nenhum.

A unificação de cadastros já resolveu esse problema do jeito certo
(``MergeAudit``: quem, quando, o que saiu de onde, e um retrato para desfazer).
Aqui se segue o mesmo espírito, com uma diferença deliberada: **o registro mora
em ``shopman/``, não em ``packages/``.** O Core não precisa saber que existe um
balcão liberando contato; quem precisa é a casa.

E há uma interação que ninguém tinha mapeado. O ``MergeService.undo`` devolve os
contatos ao cadastro absorvido pelos **PKs guardados no snapshot** — e um PK
apagado não volta. Se o contato liberado for justamente um dos que uma
unificação moveu, o desfazer daquela unificação volta INCOMPLETO, em silêncio.
Por isso ``merge_audit_id``: no ato da liberação se olha se algum ``MergeAudit``
ainda dentro da janela de 24h carrega aquele PK, e o vínculo fica gravado. A tela
de desfazer lê esse vínculo e avisa quem for desfazer.
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ReleasedContactKind(models.TextChoices):
    """O que foi solto. O vocabulário é o do balcão, não o do banco."""

    PHONE = "phone", _("WhatsApp")
    EMAIL = "email", _("e-mail")
    CPF = "cpf", _("CPF/CNPJ")


class ContactRelease(models.Model):
    """Um contato solto de um cadastro desativado, com o suficiente para refazê-lo.

    Guarda o valor, o tipo, a ficha de origem (``ref`` e nome — o ``ref`` é
    estável e sobrevive ao cadastro), o PK apagado, se ele era o principal, quem
    liberou e quando. Com isso um ``ContactPoint`` idêntico pode ser recriado à
    mão: é essa reconstrução que a reconfirmação da tela promete.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    kind = models.CharField(
        _("tipo de contato"),
        max_length=20,
        choices=ReleasedContactKind.choices,
    )
    value = models.CharField(
        _("contato liberado"),
        max_length=255,
        help_text=_("O valor normalizado, exatamente como estava gravado."),
    )

    # De QUAL ficha saiu. O ``ref`` é a chave que não muda; o nome fica junto
    # porque quem lê a trilha meses depois precisa reconhecer a pessoa sem uma
    # segunda consulta.
    released_from_ref = models.CharField(_("cadastro de origem"), max_length=50)
    released_from_name = models.CharField(_("nome do cadastro de origem"), max_length=200, blank=True)

    # O PK apagado — é ele que amarra a liberação ao snapshot de uma unificação.
    released_pk = models.CharField(_("registro apagado"), max_length=64, blank=True)
    was_primary = models.BooleanField(_("era o contato principal"), default=False)

    #: A unificação cujo DESFAZER esta liberação degrada, quando há uma.
    #:
    #: O ``undo`` devolve os contatos por PK; o PK apagado aqui não volta, e a
    #: unificação desfeita nasce incompleta. Gravar o vínculo é o que permite
    #: avisar quem for desfazer, em vez de deixá-lo descobrir pela ausência.
    merge_audit_id = models.UUIDField(_("unificação afetada"), null=True, blank=True)

    actor = models.CharField(_("quem liberou"), max_length=200, blank=True)
    released_at = models.DateTimeField(_("liberado em"), default=timezone.now)

    class Meta:
        verbose_name = _("contato liberado")
        verbose_name_plural = _("contatos liberados")
        ordering = ["-released_at"]
        indexes = [
            models.Index(fields=["released_from_ref"], name="shop_release_from_ref"),
            models.Index(fields=["merge_audit_id"], name="shop_release_merge"),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.value} ← {self.released_from_ref}"
