"""forget_customer — anonimização LGPD do lado do auth (doorman).

O bridge copia first_name/last_name do cliente para o Django User no login; a
anonimização precisa alcançá-los e revogar os dispositivos confiáveis, senão o
nome do cliente sobrevive no auth e os aparelhos seguem confiados.
"""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from shopman.doorman.models import CustomerUser, TrustedDevice, VerificationCode
from shopman.doorman.services._user_bridge import forget_customer

User = get_user_model()
pytestmark = pytest.mark.django_db


def test_forget_customer_scrubs_user_and_revokes_devices():
    cid = uuid.uuid4()
    user = User.objects.create_user(username="customer_x", first_name="Ana", last_name="Silva")
    user.email = "ana@example.com"
    user.save()
    CustomerUser.objects.create(user=user, customer_id=cid)
    TrustedDevice.create_for("customer", cid, user_agent="A")
    TrustedDevice.create_for("customer", cid, user_agent="B")

    forget_customer(cid)

    user.refresh_from_db()
    assert user.first_name == ""
    assert user.last_name == ""
    assert user.email == ""
    assert user.is_active is False
    assert TrustedDevice.objects.filter(subject_type="customer", subject_id=str(cid), is_active=True).count() == 0


def test_forget_customer_without_link_is_safe():
    # Cliente sem User vinculado (ex.: só pediu por WhatsApp) — não deve estourar.
    forget_customer(uuid.uuid4())


def test_forget_customer_apaga_o_telefone_do_vinculo_e_os_codigos():
    """O telefone é a identidade desta loja, e ele sobrevivia em dois lugares.

    Medido em 20/08 varrendo o banco depois de excluir a conta pela tela do
    storefront: `doorman_customer_user.metadata` guardava o telefone com que a
    conta nasceu, e `doorman_verification_code.target_value` guardava o número
    em cada código emitido, incluindo o que a pessoa acabou de usar para provar
    que era ela antes de mandar apagar tudo.
    """
    cid = uuid.uuid4()
    phone = "+5543991234567"
    user = User.objects.create_user(username="customer_y", first_name="Bia")
    CustomerUser.objects.create(user=user, customer_id=cid, metadata={"phone": phone})
    VerificationCode.objects.create(target_value=phone, purpose=VerificationCode.Purpose.LOGIN)
    VerificationCode.objects.create(target_value="+5543990000000", purpose=VerificationCode.Purpose.LOGIN)

    forget_customer(cid, phone=phone)

    link = CustomerUser.objects.get(customer_id=cid)
    assert link.metadata == {}
    assert not VerificationCode.objects.filter(target_value=phone).exists()
    # O código de outra pessoa não é assunto desta exclusão.
    assert VerificationCode.objects.filter(target_value="+5543990000000").exists()
