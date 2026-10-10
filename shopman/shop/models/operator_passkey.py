"""A digital do dispositivo do operador: uma credencial WebAuthn por (pessoa, dispositivo).

Decisão do dono (SUITE-UX §15, 03/10/2026): o envio do Marketing se confirma com a
digital do dispositivo, e a frase digitada fica como alternativa. A digital aqui é a
verificação de usuário do próprio dispositivo (digital, rosto, PIN do sistema): o
autenticador assina o desafio só depois de reconhecer a pessoa, e a chave privada nunca
sai dele. Do lado de cá fica só a chave pública, que verifica a assinatura.

É o par do ``doorman.Passkey`` do cliente, mas do OPERADOR: o sujeito é o usuário do
Django (``settings.AUTH_USER_MODEL``), não o cliente, e por isso mora no orquestrador e
não no Core. Os dois mundos não se misturam: uma credencial de cliente nunca confirma
um disparo, e vice-versa.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class OperatorPasskey(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="operador",
        on_delete=models.CASCADE,
        related_name="operator_passkeys",
    )
    #: O identificador que o navegador manda para dizer qual chave vai usar (base64url).
    credential_id = models.CharField("ID da credencial", max_length=512, unique=True, db_index=True)
    #: A chave PÚBLICA (base64url, formato COSE). Só verifica assinatura.
    public_key = models.TextField("chave pública")
    #: Contador anti-replay. Credencial sincronizada reporta 0 sempre; só comparamos acima de 0.
    sign_count = models.BigIntegerField("contador de assinatura", default=0)
    transports = models.JSONField("transportes", default=list, blank=True)
    #: O nome que a pessoa reconhece ("Celular da Ana"), para revogar sem adivinhar.
    label = models.CharField("apelido", max_length=100, blank=True, default="")
    created_at = models.DateTimeField("cadastrada em", auto_now_add=True)
    last_used_at = models.DateTimeField("usada em", null=True, blank=True)

    class Meta:
        verbose_name = "digital do dispositivo"
        verbose_name_plural = "digitais dos dispositivos"
        ordering = ["-last_used_at", "-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"], name="shop_oppasskey_user_created")]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        return self.label or f"digital {self.credential_id[:12]}"

    def touch(self, *, sign_count: int | None = None) -> None:
        """Registrar uso. O contador só sobe."""
        fields = ["last_used_at"]
        self.last_used_at = timezone.now()
        if sign_count is not None and sign_count > self.sign_count:
            self.sign_count = sign_count
            fields.append("sign_count")
        self.save(update_fields=fields)
