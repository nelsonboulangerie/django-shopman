"""Incidentes: a credencial da ponte do GitHub e o placar dos remédios.

``IncidentReaderCredential``: credencial de leitura da ponte (GitHub Actions).

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


class IncidentAction(models.Model):
    """Uma decisão do acionador sobre um alerta: o placar dos remédios.

    Toda decisão vira linha, inclusive a de NÃO agir (fora da regra, teto, prazo
    vencido), para que o placar diga o que o sistema fez, o que deixou para gente e
    por quê. ``detail`` nunca leva dado de cliente: refs, códigos e motivos.
    """

    RAN = "ran"
    RESOLVED = "resolved"
    NOT_RESOLVED = "not_resolved"
    WOULD_RUN = "would_run"
    REFUSED = "refused"
    SKIPPED = "skipped"
    CEILING = "ceiling"
    OUTCOMES = [
        (RAN, "Acionado, conferindo"),
        (RESOLVED, "Resolveu"),
        (NOT_RESOLVED, "Não resolveu"),
        (WOULD_RUN, "Acionaria (sombra)"),
        (REFUSED, "O domínio recusou"),
        (SKIPPED, "Fica com gente"),
        (CEILING, "Teto de tentativas"),
    ]

    alert_id = models.PositiveBigIntegerField("alerta", null=True, blank=True, db_index=True)
    alert_type = models.CharField("tipo do alerta", max_length=50, db_index=True)
    target = models.CharField("alvo", max_length=80, help_text="Ref do pedido, ou o tipo quando não há pedido.")
    remedy = models.CharField("remédio", max_length=40, blank=True, default="")
    decided_by = models.CharField("quem decidiu", max_length=80, default="regra")
    confidence = models.FloatField("confiança", null=True, blank=True)
    mode = models.CharField("modo", max_length=10, default="on")
    outcome = models.CharField("desfecho", max_length=16, choices=OUTCOMES, db_index=True)
    detail = models.CharField("detalhe", max_length=300, blank=True, default="")
    #: Custo da leitura da IA em micro-dólares (1 = US$ 0,000001), inteiro como o ``AiInvocation``.
    cost_usd_micros = models.PositiveBigIntegerField("custo (micro-US$)", default=0)
    created_at = models.DateTimeField("decidido em", auto_now_add=True, db_index=True)
    verified_at = models.DateTimeField("conferido em", null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "decisão de remédio"
        verbose_name_plural = "placar dos remédios"
        indexes = [models.Index(fields=["remedy", "target", "created_at"], name="backstage_incact_target_idx")]

    def __str__(self) -> str:
        return f"{self.alert_type} · {self.get_outcome_display()}"
