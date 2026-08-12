"""Trusted-device mutation service for customer-facing entry points."""

from __future__ import annotations

import json
import logging
import urllib.request
import uuid

from django.core.cache import cache

logger = logging.getLogger(__name__)


def cookie_name() -> str:
    from shopman.doorman.conf import doorman_settings

    return doorman_settings.DEVICE_TRUST_COOKIE_NAME


def _geolocate_ip(ip: str) -> str:
    """Resolve IP to city/region via ip-api.com, cached for the account surface."""
    if not ip or ip.startswith("127.") or ip.startswith("10.") or ip == "::1":
        return ""

    cache_key = f"geo:{ip}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        url = f"http://ip-api.com/json/{ip}?fields=city,regionName,country&lang=pt-BR"
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read())
        if data.get("city"):
            location = f"{data['city']}, {data.get('regionName', '')}"
            cache.set(cache_key, location, 86400)
            return location
    except Exception:
        logger.exception("geolocate_ip_failed ip=%s", ip)

    cache.set(cache_key, "", 3600)
    return ""


def list_devices(*, customer_id, raw_token: str | None) -> list[dict]:
    from shopman.doorman import TrustedDevice, hash_device_token
    from shopman.doorman.models.device_trust import SubjectType

    # ⚠️ Era `filter(customer_id=...)`, e esse campo não existe mais: o model passou a usar
    # sujeito tipado (cliente ou display). O resultado era 500 em toda visita à tela de
    # segurança — e como o SSR aguarda este fetch, a página inteira virava "Tivemos um
    # problema por aqui". A consulta agora tem dono no model.
    devices = TrustedDevice.active_for(SubjectType.CUSTOMER, customer_id)

    current_hash = hash_device_token(raw_token) if raw_token else None

    device_list = []
    for device in devices:
        if not device.is_valid:
            continue

        location = _geolocate_ip(device.ip_address) if device.ip_address else ""
        device_list.append({
            "id": str(device.id),
            "label": device.label.replace(" / ", " no ") if device.label else "",
            "created_at": device.created_at,
            "last_used_at": device.last_used_at,
            "location": location,
            "is_current": current_hash is not None and device.token_hash == current_hash,
        })

    return device_list


def revoke_device(*, customer_id, device_id: str) -> str | None:
    """Revoke one active trusted device.

    Returns ``None`` when the device was revoked or already gone, otherwise an
    operator-facing validation message for the view.
    """
    from shopman.doorman import TrustedDevice

    try:
        device_uuid = uuid.UUID(str(device_id))
    except ValueError:
        return "ID inválido."

    from shopman.doorman.models.device_trust import SubjectType

    device = TrustedDevice.active_for(SubjectType.CUSTOMER, customer_id).filter(
        id=device_uuid,
    ).first()
    if device is None:
        # Já revogado, inexistente, ou de OUTRA pessoa: a mesma resposta para os três, porque
        # distinguir contaria a quem tenta quais ids existem.
        return None

    device.revoke()
    logger.info("Trusted device revoked", extra={"device_id": str(device.id)})
    return None


def revoke_all(*, customer_id) -> int:
    from shopman.doorman.services.device_trust import DeviceTrustService

    count = DeviceTrustService.revoke_all(customer_id)
    logger.info(
        "All trusted devices revoked",
        extra={"customer_id": str(customer_id), "count": count},
    )
    return count
