"""A lápide que impede a conta excluída de voltar pela porta do provedor.

Apagar o vínculo local não basta: o assinante continua existindo no ManyChat, e
o próximo webhook dele chega com nome e telefone, não encontra ninguém (o
identificador acabou de ser apagado) e **cria um cadastro novo** com os dados
que o titular acabou de mandar apagar. Era por causa desse caminho que a
exclusão preferia recusar a mentir — ver
`docs/plans/PRIVACY-CANONICAL-FENCE-MATRIX-2026-09-16.md`.

A lápide fecha esse caminho sem guardar o dado: grava só um HMAC do
identificador do assinante, o bastante para reconhecer quem volta e recusar.

⚠️ O que a lápide NÃO faz: apagar a pessoa lá dentro. A API pública do ManyChat
não tem verbo de exclusão de assinante (nove endpoints usados nesta casa, nenhum
apaga), então a linha de contato de lá sai pela mão de um humano na interface
deles — é o que a tarefa `manychat_contact_erasure_due` cobra, com prazo.
"""

from __future__ import annotations

import hashlib
import hmac

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def erasure_digest(provider: str, handle_type: str, value: str) -> str:
    """HMAC com separação de domínio — a lápide nunca guarda o valor em claro.

    SHA-256 puro não serviria: o espaço de telefones brasileiros (e o de ids
    sequenciais de assinante) cabe num laptop, então o hash seria o número com
    outra roupa. O mesmo argumento já está escrito em `anonymize_customer`.

    ⚠️ Trocar a ``SECRET_KEY`` invalida toda lápide já gravada, e ela NÃO pode
    ser regravada: o valor de origem foi apagado exatamente por ser pessoal.
    Rotação de chave reabre, em silêncio, o caminho de ressurreição.
    """
    material = f"provider-erasure:v1:{provider}:{handle_type}:{str(value).strip()}"
    return hmac.new(settings.SECRET_KEY.encode(), material.encode(), hashlib.sha256).hexdigest()


class ProviderErasureTombstone(models.Model):
    """Marca que um identificador de provedor pertenceu a uma conta excluída."""

    class Provider(models.TextChoices):
        MANYCHAT = "manychat", _("ManyChat")

    class HandleType(models.TextChoices):
        SUBSCRIBER_ID = "subscriber_id", _("identificador do assinante")

    provider = models.CharField("provedor", max_length=32, choices=Provider.choices)
    handle_type = models.CharField("tipo do identificador", max_length=24, choices=HandleType.choices)
    digest = models.CharField("digest do identificador", max_length=64, db_index=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        app_label = "guestman"
        verbose_name = "lápide de exclusão"
        verbose_name_plural = "lápides de exclusão"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "handle_type", "digest"],
                name="guestman_provider_erasure_uq",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return f"ProviderErasureTombstone({self.provider}/{self.handle_type})"

    @classmethod
    def remember(cls, *, provider: str, handle_type: str, value: str) -> bool:
        """Grava a lápide; repetir é seguro e não é erro."""
        value = str(value or "").strip()
        if not value:
            return False
        _, created = cls.objects.get_or_create(
            provider=provider,
            handle_type=handle_type,
            digest=erasure_digest(provider, handle_type, value),
        )
        return created

    @classmethod
    def matches(cls, *, provider: str, handle_type: str, value: str) -> bool:
        """Responde se este identificador já foi objeto de um pedido de exclusão."""
        value = str(value or "").strip()
        if not value:
            return False
        return cls.objects.filter(
            provider=provider,
            handle_type=handle_type,
            digest=erasure_digest(provider, handle_type, value),
        ).exists()
