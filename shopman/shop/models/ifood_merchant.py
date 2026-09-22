"""Loja aberta no iFood: as interrupções que o Shopman criou e o último status lido.

O Shopman é a fonte da verdade de "a loja está aberta" (``business_calendar``).
Duas coisas precisam de memória durável para que o iFood diga o mesmo:

* :class:`IFoodInterruption` — cada interrupção que o **Shopman** pediu ao iFood,
  seja porque o calendário fechou um dia que a grade semanal abriria (feriado,
  fechamento pontual), seja porque o gestor pausou a loja no iFood. A linha é a
  trilha: quem pediu, quando, por quê, e quem retomou. É por ela que o Shopman
  distingue a pausa DELE de uma pausa feita no Portal do Parceiro — o iFood não
  marca a origem.
* :class:`IFoodStoreStatus` — o último ``GET /status`` do iFood, e desde quando
  ele diverge da casa. Mora no banco (e não no cache) porque quem lê é outro
  processo: o maintenance-worker grava, o Gestor mostra.

Nada disso é escrito enquanto ``SHOPMAN_IFOOD["merchant_sync_enabled"]`` estiver
desligado. Ver ``shopman/shop/services/ifood_merchant.py``.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class IFoodInterruptionKind(models.TextChoices):
    CALENDAR = "calendar", "Calendário da loja"
    MANUAL = "manual", "Pausa do gestor"


class IFoodInterruptionState(models.TextChoices):
    # Pedida ao iFood, ainda sem resposta (a directive está na fila).
    PENDING_CREATE = "pending_create", "Pedindo ao iFood"
    ACTIVE = "active", "Em vigor no iFood"
    # Retomada pedida, ainda sem resposta.
    PENDING_REMOVE = "pending_remove", "Retomando no iFood"
    REMOVED = "removed", "Retomada"
    # O iFood recusou (ex.: já existe outra pausa no mesmo horário). Não há retry:
    # o motivo fica em ``last_error`` e aparece para quem pediu.
    FAILED = "failed", "Recusada pelo iFood"


class IFoodInterruption(models.Model):
    kind = models.CharField("origem", max_length=16, choices=IFoodInterruptionKind.choices)
    state = models.CharField(
        "situação",
        max_length=16,
        choices=IFoodInterruptionState.choices,
        default=IFoodInterruptionState.PENDING_CREATE,
    )
    merchant_id = models.CharField("loja no iFood", max_length=64)
    # Id que o iFood devolve no POST; vazio até a criação ser confirmada.
    ifood_id = models.CharField("id no iFood", max_length=100, blank=True)
    # Texto enviado ao iFood (``description``, até 255 caracteres).
    description = models.CharField("descrição enviada", max_length=255)
    # Motivo que o gestor escreveu; vazio nas interrupções do calendário.
    reason = models.CharField("motivo", max_length=255, blank=True)
    starts_at = models.DateTimeField("início")
    ends_at = models.DateTimeField("fim")
    # Identidade da interrupção do calendário (ex.: "2026-12-25..2026-12-25"):
    # é por ela que a reconciliação sabe o que já pediu.
    calendar_key = models.CharField("dias do calendário", max_length=32, blank=True, db_index=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="pedida por",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    requested_at = models.DateTimeField("pedida em", auto_now_add=True)
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="retomada por",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    removed_at = models.DateTimeField("retomada em", null=True, blank=True)
    last_error = models.TextField("último erro", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "interrupção no iFood"
        verbose_name_plural = "interrupções no iFood"
        ordering = ("-requested_at",)

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.starts_at:%d/%m %H:%M}–{self.ends_at:%d/%m %H:%M}"


class IFoodStoreStatus(models.Model):
    """Último status do iFood para uma loja. Uma linha por ``merchant_id``."""

    merchant_id = models.CharField("loja no iFood", max_length=64, unique=True)
    checked_at = models.DateTimeField("conferido em", null=True, blank=True)
    # Verdade do iFood: alguma operação (DELIVERY/TAKEOUT…) recebe pedido agora.
    available = models.BooleanField("recebendo pedidos no iFood", default=False)
    # Pior estado entre as operações: OK, WARNING, CLOSED, ERROR, UNAVAILABLE.
    state = models.CharField("estado no iFood", max_length=16, blank=True)
    # As validações que não passaram, já resumidas: [{code, state, title}].
    problems = models.JSONField("validações com problema", default=list, blank=True)
    # O que a casa esperava ver no iFood no mesmo instante.
    expected_available = models.BooleanField("a casa esperava aberta", default=False)
    # Desde quando iFood e casa discordam; nulo quando concordam. O alerta só sai
    # quando a divergência sobrevive a uma conferência inteira — o iFood aplica
    # pausa e horário de forma assíncrona, e um instante de atraso não é defeito.
    divergent_since = models.DateTimeField("divergente desde", null=True, blank=True)
    # A última falha de leitura (sem token, recusa, 5xx). Vazio quando leu.
    last_error = models.TextField("último erro", blank=True)
    # Última vez que horário e calendário foram conferidos e gravados no iFood.
    synced_at = models.DateTimeField("horário gravado em", null=True, blank=True)

    class Meta:
        verbose_name = "status da loja no iFood"
        verbose_name_plural = "status da loja no iFood"

    def __str__(self) -> str:
        return f"{self.merchant_id}: {self.state or '—'}"
