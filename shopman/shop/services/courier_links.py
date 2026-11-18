"""O link da rota para o entregador da casa: emitir, abrir, fechar e revogar.

Plano: ``docs/plans/DELIVERY-MULTI-SERVICE-PLAN.md`` §4.2 e §4.4 (DEV-2026-030, frente M2a).
Regras, todas decididas no plano:

- Um link vivo por rota. Emitir de novo (troca de entregador, reenvio) revoga o anterior.
- O link se prende ao celular que CONFIRMA ser do entregador ("Sou o Diego, abrir"), não
  ao primeiro que o abre (dono, 17/11): quem abre por curiosidade ou sem querer (um
  operador da casa, por exemplo) vê só o nome de quem é a rota e não prende nada. Guardamos
  só o hash da chave do celular; outro celular depois disso vê "aberto em outro celular".
- O balcão pode soltar o link (``release``) quando ele ficou preso no celular errado ou o
  entregador trocou de celular; o próximo a confirmar fica com ele.
- Ele vence 2 h depois de a rota fechar, e morre na hora quando a rota é cancelada.

Quem decide o que a tela mostra para cada estado é a página do entregador (M2); aqui só se
responde o estado.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from shopman.shop.models.delivery_service import Courier, CourierLink

#: Quanto o link vive depois de a rota fechar (plano §4.4).
LINK_GRACE = timedelta(hours=2)
#: A chave do celular é gerada pela página; abaixo disso não é chave, é chute.
MIN_DEVICE_KEY = 16

#: Estados de uma tentativa de abrir o link.
OK = "ok"
UNKNOWN = "unknown"
REVOKED = "revoked"
EXPIRED = "expired"
OTHER_DEVICE = "other_device"
BAD_DEVICE = "bad_device"
#: O link ainda não foi confirmado por celular nenhum: a página pede a confirmação e não
#: mostra nada da rota além do nome do entregador.
UNCLAIMED = "unclaimed"

#: Motivos de revogação.
REISSUED = "reissued"
CANCELLED = "cancelled"
REASSIGNED = "reassigned"


@dataclass(frozen=True)
class LinkAccess:
    state: str
    link: CourierLink | None = None

    @property
    def ok(self) -> bool:
        return self.state == OK


def _hash(device_key: str) -> str:
    return hashlib.sha256(device_key.encode("utf-8")).hexdigest()


def _live(ride_ref: str):
    return CourierLink.objects.select_for_update().filter(ride_ref=ride_ref, revoked_at__isnull=True)


@transaction.atomic
def issue(courier: Courier, ride_ref: str, order_refs: list[str], *, now: datetime | None = None) -> CourierLink:
    """Emite o link da rota para o entregador, revogando o que estiver vivo para a mesma rota."""
    if not ride_ref:
        raise ValueError("A rota precisa de um identificador.")
    if not order_refs:
        raise ValueError("A rota precisa de pelo menos um pedido.")
    now = now or timezone.now()
    previous = list(_live(ride_ref))
    for link in previous:
        link.revoked_at = now
        link.revoked_reason = REASSIGNED if link.courier_id != courier.pk else REISSUED
        link.save(update_fields=["revoked_at", "revoked_reason"])
    return CourierLink.objects.create(
        token=secrets.token_urlsafe(32),
        courier=courier,
        ride_ref=ride_ref,
        order_refs=list(order_refs),
    )


def _check(link: CourierLink | None, device_key: str, now: datetime) -> str | None:
    if link is None:
        return UNKNOWN
    if link.revoked_at is not None:
        return REVOKED
    if link.expires_at is not None and now >= link.expires_at:
        return EXPIRED
    if not device_key or len(device_key) < MIN_DEVICE_KEY:
        return BAD_DEVICE
    if link.device_hash and link.device_hash != _hash(device_key):
        return OTHER_DEVICE
    return None


@transaction.atomic
def resolve(token: str, device_key: str, *, now: datetime | None = None) -> LinkAccess:
    """Abre o link: diz se este celular pode ver a rota. Abrir não prende nada."""
    now = now or timezone.now()
    link = CourierLink.objects.select_for_update().filter(token=token).first() if token else None
    refused = _check(link, device_key, now)
    if refused:
        return LinkAccess(refused, link)
    if not link.device_hash:
        return LinkAccess(UNCLAIMED, link)
    link.last_seen_at = now
    link.save(update_fields=["last_seen_at"])
    return LinkAccess(OK, link)


@transaction.atomic
def claim(token: str, device_key: str, *, now: datetime | None = None) -> LinkAccess:
    """ "Sou o Diego, abrir": prende o link a este celular. Repetir no mesmo celular é inócuo."""
    now = now or timezone.now()
    link = CourierLink.objects.select_for_update().filter(token=token).first() if token else None
    refused = _check(link, device_key, now)
    if refused:
        return LinkAccess(refused, link)
    fields = ["last_seen_at"]
    link.last_seen_at = now
    if not link.device_hash:
        link.device_hash = _hash(device_key)
        link.opened_at = now
        fields += ["device_hash", "opened_at"]
    link.save(update_fields=fields)
    return LinkAccess(OK, link)


@transaction.atomic
def release(ride_ref: str) -> CourierLink | None:
    """O balcão solta o link do celular em que ele está preso; o próximo a confirmar fica com ele."""
    link = _live(ride_ref).first()
    if link is None:
        return None
    link.device_hash = ""
    link.opened_at = None
    link.save(update_fields=["device_hash", "opened_at"])
    return link


@transaction.atomic
def close(ride_ref: str, *, at: datetime | None = None) -> CourierLink | None:
    """A rota fechou: o link vive mais ``LINK_GRACE`` e depois vence."""
    at = at or timezone.now()
    link = _live(ride_ref).first()
    if link is None:
        return None
    link.expires_at = at + LINK_GRACE
    link.save(update_fields=["expires_at"])
    return link


@transaction.atomic
def revoke(ride_ref: str, *, reason: str = CANCELLED, now: datetime | None = None) -> CourierLink | None:
    """A rota foi cancelada (ou o entregador trocado por fora): o link morre na hora."""
    now = now or timezone.now()
    link = _live(ride_ref).first()
    if link is None:
        return None
    link.revoked_at = now
    link.revoked_reason = reason
    link.save(update_fields=["revoked_at", "revoked_reason"])
    return link
