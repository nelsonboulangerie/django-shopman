"""
User bridge — get or create Django User for a Customer.

Extracted from AccessLinkService for reuse by PhoneOTPBackend and other
authentication paths.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError

from ..models import CustomerUser
from ..protocols.customer import AuthCustomerInfo

logger = logging.getLogger("shopman.doorman.user_bridge")
User = get_user_model()


def get_or_create_user_for_customer(customer: AuthCustomerInfo) -> tuple:
    """
    Get or create a Django User for a Customer.

    Handles concurrent creation via IntegrityError retry.

    Args:
        customer: Customer info from resolver.

    Returns:
        (User, created: bool) tuple.
    """
    # Check existing link
    try:
        link = CustomerUser.objects.select_related("user").get(
            customer_id=customer.uuid,
        )
        return link.user, False
    except CustomerUser.DoesNotExist:
        pass

    # Create User
    username = f"customer_{str(customer.uuid).replace('-', '')[:12]}"
    user = User.objects.create_user(username=username)

    # Set name from customer
    if customer.name:
        parts = customer.name.split(" ", 1)
        user.first_name = parts[0]
        if len(parts) > 1:
            user.last_name = parts[1]
        user.save(update_fields=["first_name", "last_name"])

    # Create link — retry on concurrent creation.
    # O telefone vai no `metadata` (JSONField que já existe — sem migração) para
    # que o vínculo seja RELIGÁVEL: ele guarda o uuid do Customer, e quando os
    # clientes são recriados (reseed, reset de base, migração) os uuids mudam e o
    # login fica apontando para o vazio. Sem telefone não há como reencontrar o
    # cliente atual, e o vínculo só pode ser descartado. Ver
    # `manage.py cleanup_orphan_customer_links`.
    try:
        CustomerUser.objects.create(
            user=user,
            customer_id=customer.uuid,
            metadata={"phone": customer.phone or ""},
        )
    except IntegrityError:
        # Another request already created the link; use that one
        user.delete()
        link = CustomerUser.objects.select_related("user").get(
            customer_id=customer.uuid,
        )
        return link.user, False

    logger.info(
        "User created for customer",
        extra={"customer_id": str(customer.uuid), "user_id": user.id},
    )

    return user, True


def forget_customer(customer_uuid, phone: str = "") -> None:
    """Anonimiza o User Django vinculado e revoga os dispositivos confiáveis (LGPD).

    O bridge copia first_name/last_name do cliente para o User no login; a
    anonimização precisa alcançá-los, senão o nome sobrevive no auth. Também
    desativa o login, revoga TrustedDevices, zera o `metadata` do vínculo e
    apaga os códigos de verificação emitidos para o telefone.

    ``phone`` é o número original do titular, e vem do chamador porque o código
    OTP é indexado pelo DESTINO (`target_value`), não pelo cliente: sem ele,
    quem excluiu a conta agora mesmo deixava o próprio telefone no banco, no
    código que acabou de usar para provar que era ele. Idempotente e defensivo.
    """
    from ..models import TrustedDevice, VerificationCode

    try:
        link = CustomerUser.objects.select_related("user").get(customer_id=customer_uuid)
    except CustomerUser.DoesNotExist:
        link = None
    except Exception:
        logger.warning("forget_customer: lookup do User falhou", exc_info=True)
        link = None

    if link is not None:
        user = link.user
        user.first_name = ""
        user.last_name = ""
        user.email = ""
        user.is_active = False
        user.save(update_fields=["first_name", "last_name", "email", "is_active"])
        # O `metadata` do vínculo guarda o telefone com que a conta nasceu, e a
        # varredura do banco depois de uma exclusão feita pela tela ainda o
        # encontrava ali. Nesta loja o telefone É a identidade (é o único
        # login), então deixá-lo no vínculo é deixar a pessoa identificável.
        if link.metadata:
            link.metadata = {}
            link.save(update_fields=["metadata"])

    try:
        TrustedDevice.revoke_all_for("customer", customer_uuid)
    except Exception:
        logger.warning("forget_customer: revogação de devices falhou", exc_info=True)

    if phone:
        try:
            VerificationCode.objects.filter(target_value=phone).delete()
        except Exception:
            logger.warning("forget_customer: limpeza de códigos OTP falhou", exc_info=True)
