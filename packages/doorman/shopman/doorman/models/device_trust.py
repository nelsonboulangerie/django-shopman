"""
TrustedDevice model — Device trust for skip-OTP on repeat logins.

When a user successfully verifies via OTP, we can mark their device as trusted.
On subsequent logins from the same device, we skip the full OTP flow.

Security:
- Device identified by a secure random token stored in a HttpOnly cookie.
- Token stored as HMAC digest in DB (never plaintext).
- TTL-based expiration (default 30 days).
- Can be revoked per-customer or globally.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def _get_hmac_key() -> bytes:
    """Get the HMAC key for device token hashing."""
    return settings.SECRET_KEY.encode("utf-8")


def _hash_token(raw_token: str) -> str:
    """Compute HMAC-SHA256 hex digest for a device token."""
    return hmac.new(
        _get_hmac_key(), raw_token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _default_expires_at():
    from ..conf import doorman_settings

    return timezone.now() + timedelta(days=doorman_settings.DEVICE_TRUST_TTL_DAYS)


class SubjectType(models.TextChoices):
    """De quem — ou de quê — este dispositivo é confiável.

    Confiança de dispositivo é "este navegador já foi verificado para X, então não
    verifique de novo". O X não precisa ser uma pessoa: um quadro de menu na parede
    é um navegador autorizado a ler um quadro, e a forma é a mesma.

    Segue ``handle_type`` + ``handle_ref`` da constituição §3.1 — chave de vínculo
    com ator/canal/contexto — e por isso o sujeito é textual, não UUID: cliente é
    identificado por UUID, display por ``ref`` de canal.

    ``operator`` continua NÃO existindo, e a distinção é o ponto: o terceiro valor
    é a ESTAÇÃO, não a pessoa. Lembrar quem opera seria lembrar de gente; lembrar a
    estação é lembrar de um aparelho — o balcão, o totem —, que é justamente o que
    não muda quando o turno troca.

    ``station`` foi previsto aqui em 21/08/2026 (D1, opção B). O que ele guarda é a
    resposta para "de que balcão esta requisição veio", e nada além disso: a
    estação confiável NÃO ganha permissão nenhuma por ser confiável. Quem autoriza
    é a pessoa que se identifica nela. Uma chave que só abre a antessala.

    ``subject_id`` é o ``ref`` do ``cashman.Terminal``, do mesmo jeito que o
    ``display`` usa o ``ref`` do canal.
    """

    CUSTOMER = "customer", _("cliente")
    DISPLAY = "display", _("quadro")
    STATION = "station", _("estação")


class TrustedDevice(models.Model):
    """
    Um dispositivo confiável para um sujeito (cliente, quadro ou estação).

    Cliente: depois da verificação por OTP, um cookie seguro fica no dispositivo, e
    no acesso seguinte daquele navegador o cliente pula o OTP.

    Display: um quadro de menu autorizado uma vez por operador continua abrindo, sem
    login e sem credencial na URL — revogável por dispositivo no Admin.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Sujeito tipado (sem FK — mesmo padrão de desacoplamento de sempre)
    subject_type = models.CharField(
        _("tipo de sujeito"),
        max_length=16,
        choices=SubjectType.choices,
        default=SubjectType.CUSTOMER,
        db_index=True,
    )
    subject_id = models.CharField(
        _("ID do sujeito"),
        max_length=64,
        db_index=True,
        help_text=_("UUID do cliente no Guestman, ou ref do canal de exibição."),
    )

    # Device identification (HMAC of the cookie token)
    token_hash = models.CharField(
        _("hash do token"),
        max_length=64,
        unique=True,
        db_index=True,
        help_text=_("HMAC-SHA256 do token do cookie."),
    )

    # Device metadata
    user_agent = models.CharField(
        _("navegador"), max_length=512, blank=True, default=""
    )
    ip_address = models.GenericIPAddressField(
        _("endereço IP"), null=True, blank=True
    )
    label = models.CharField(
        _("rótulo"),
        max_length=100,
        blank=True,
        default="",
        help_text=_("Ex: 'Chrome no iPhone', derivado do user-agent."),
    )

    # Lifecycle
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    expires_at = models.DateTimeField(_("expira em"), default=_default_expires_at)
    last_used_at = models.DateTimeField(_("último uso"), null=True, blank=True)
    is_active = models.BooleanField(_("ativo"), default=True)

    class Meta:
        db_table = "doorman_trusted_device"
        verbose_name = _("dispositivo confiável")
        verbose_name_plural = _("dispositivos confiáveis")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["subject_type", "subject_id", "is_active"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        status = "active" if self.is_valid else "expired"
        return f"Device {self.token_hash[:8]}… for {self.subject_type} {self.subject_id} ({status})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return self.is_active and not self.is_expired

    def touch(self):
        """Update last_used_at timestamp."""
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])

    def revoke(self):
        """Revoke this trusted device."""
        self.is_active = False
        self.save(update_fields=["is_active"])

    # ===========================================
    # Class methods
    # ===========================================

    @classmethod
    def create_for(
        cls,
        subject_type: str,
        subject_id: str,
        user_agent: str = "",
        ip_address: str | None = None,
        label: str = "",
    ) -> tuple["TrustedDevice", str]:
        """
        Create a trusted device and return (device, raw_token).

        The raw_token should be stored in a secure HttpOnly cookie.
        The DB only stores the HMAC digest.
        """
        raw_token = secrets.token_urlsafe(32)
        device = cls.objects.create(
            subject_type=subject_type,
            subject_id=str(subject_id),
            token_hash=_hash_token(raw_token),
            user_agent=user_agent[:512],
            ip_address=ip_address,
            label=label or _derive_label(user_agent),
        )
        return device, raw_token

    @classmethod
    def verify_token(cls, raw_token: str) -> "TrustedDevice | None":
        """
        Verify a raw device token against stored hashes.

        Returns the TrustedDevice if valid, None otherwise.
        Uses HMAC comparison for timing-safety.
        """
        token_hash = _hash_token(raw_token)
        try:
            device = cls.objects.get(token_hash=token_hash)
        except cls.DoesNotExist:
            return None

        if not device.is_valid:
            return None

        device.touch()
        return device

    @classmethod
    def active_for(cls, subject_type: str, subject_id: str):
        """Os dispositivos ATIVOS de um sujeito, do mais recente ao mais antigo.

        ⚠️ Existe porque quem quis essa lista escrevia o filtro na unha, e o filtro mudou: o
        model passou a ter `subject_type`/`subject_id` (sujeito tipado: cliente ou display) e
        `customer_id` deixou de existir. `shop/services/devices.py` continuou filtrando pelo
        campo antigo, e a tela "Segurança e dados" passou a devolver 500 — a página inteira
        virava "Tivemos um problema por aqui", porque o SSR aguarda esse fetch.

        Um dono para a consulta é o que evita a próxima vez: refatorar o model volta a ser
        seguro quando não há cópia do filtro espalhada.
        """
        return cls.objects.filter(
            subject_type=subject_type, subject_id=str(subject_id), is_active=True,
        ).order_by("-last_used_at", "-created_at")

    @classmethod
    def revoke_all_for(cls, subject_type: str, subject_id: str) -> int:
        """Revoke every trusted device of one subject."""
        return cls.objects.filter(
            subject_type=subject_type, subject_id=str(subject_id), is_active=True
        ).update(is_active=False)

    @classmethod
    def cleanup_expired(cls, days: int = 7) -> int:
        """Delete expired devices older than N days."""
        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = cls.objects.filter(expires_at__lt=cutoff).delete()
        return deleted


def _derive_label(user_agent: str) -> str:
    """Derive a human-readable label from user-agent string."""
    if not user_agent:
        return ""
    ua = user_agent.lower()
    parts = []
    if "chrome" in ua and "edg" not in ua:
        parts.append("Chrome")
    elif "firefox" in ua:
        parts.append("Firefox")
    elif "safari" in ua and "chrome" not in ua:
        parts.append("Safari")
    elif "edg" in ua:
        parts.append("Edge")

    if "iphone" in ua:
        parts.append("iPhone")
    elif "android" in ua:
        parts.append("Android")
    elif "macintosh" in ua or "mac os" in ua:
        parts.append("Mac")
    elif "windows" in ua:
        parts.append("Windows")
    elif "linux" in ua:
        parts.append("Linux")

    return " / ".join(parts) if parts else ""
