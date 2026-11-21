"""Credencial de leitura da ponte de incidentes (GitHub Actions).

Máquina, não pessoa: lê só o resumo de incidentes, nada mais. O bearer é
``<ref>.<segredo>``; o banco guarda o HMAC e os seis últimos caracteres.
Emitida por ``issue_incident_reader_credential`` (o segredo aparece uma vez) e
revogada no Admin desmarcando "ativa".
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class IncidentReaderCredential(models.Model):
    ref = models.UUIDField("referência", default=uuid.uuid4, unique=True, editable=False)
    label = models.CharField("rótulo", max_length=120, blank=True, default="")
    token_digest = models.CharField("digest do token", max_length=64, editable=False)
    token_hint = models.CharField("final do token", max_length=8, editable=False)
    is_active = models.BooleanField("ativa", default=True)
    expires_at = models.DateTimeField("vale até")
    last_seen_at = models.DateTimeField("lida por último em", null=True, blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "credencial da ponte de incidentes"
        verbose_name_plural = "credenciais da ponte de incidentes"

    def __str__(self) -> str:
        return f"{self.label or 'Ponte de incidentes'} · …{self.token_hint}"

    @staticmethod
    def _digest(secret: str) -> str:
        key = str(settings.SECRET_KEY).encode("utf-8")
        return hmac.new(key, secret.encode("utf-8"), hashlib.sha256).hexdigest()

    @classmethod
    def issue(cls, *, label: str, expires_at) -> tuple[IncidentReaderCredential, str]:
        secret = secrets.token_urlsafe(32)
        credential = cls.objects.create(
            label=str(label or "").strip(),
            token_digest=cls._digest(secret),
            token_hint=secret[-6:],
            expires_at=expires_at,
        )
        return credential, f"{credential.ref}.{secret}"

    @classmethod
    def verify(cls, bearer: str) -> IncidentReaderCredential | None:
        ref, separator, secret = str(bearer or "").strip().partition(".")
        if not separator or not secret:
            return None
        try:
            ref_uuid = uuid.UUID(ref)
        except ValueError:
            return None
        credential = cls.objects.filter(ref=ref_uuid, is_active=True, expires_at__gt=timezone.now()).first()
        if credential is None or not hmac.compare_digest(credential.token_digest, cls._digest(secret)):
            return None
        cls.objects.filter(pk=credential.pk).update(last_seen_at=timezone.now())
        return credential
