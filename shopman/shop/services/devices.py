"""Trusted-device mutation service for customer-facing entry points."""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def cookie_name() -> str:
    from shopman.doorman.conf import doorman_settings

    return doorman_settings.DEVICE_TRUST_COOKIE_NAME


def list_devices(*, customer_id, raw_token: str | None) -> list[dict]:
    """Os aparelhos confiáveis do titular, para a tela "Segurança e dados".

    ⚠️ NÃO enriqueça esta lista com serviço de terceiro. Até 23/09/2026 havia aqui um
    `_geolocate_ip()` que mandava o IP do titular para o `ip-api.com`, em HTTP puro, sem
    TLS, a cada carga da tela, só para escrever "Londrina, Paraná" ao lado do
    aparelho. IP de titular é dado pessoal sob a LGPD, e esse terceiro não constava da
    lista de operadores da política de privacidade, que se declara "a lista inteira".
    O que a casa ganhava (um rótulo de cidade) não pagava o que a casa mandava para fora.

    A tela continua respondendo "fui eu que entrei?" com o que nunca precisou sair daqui:
    o navegador e o aparelho (`label`), quando foi o último uso, quando foi registrado, e
    o selo "Este aparelho" no que a pessoa está segurando agora. O IP segue GRAVADO em
    `TrustedDevice.ip_address` e continua visível ao próprio titular na exportação LGPD e
    ao operador no Admin — guardar é uma coisa, mandar para fora é outra.
    """
    from shopman.doorman import SubjectType, TrustedDevice, hash_device_token

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

        device_list.append({
            "id": str(device.id),
            "label": device.label.replace(" / ", " no ") if device.label else "",
            "created_at": device.created_at,
            "last_used_at": device.last_used_at,
            "is_current": current_hash is not None and device.token_hash == current_hash,
        })

    return device_list


def revoke_device(*, customer_id, device_id: str) -> str | None:
    """Revoke one active trusted device.

    Returns ``None`` when the device was revoked or already gone, otherwise an
    operator-facing validation message for the view.
    """
    from shopman.doorman import SubjectType, TrustedDevice

    try:
        device_uuid = uuid.UUID(str(device_id))
    except ValueError:
        return "ID inválido."

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
