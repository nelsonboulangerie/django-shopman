"""Vínculo de login órfão: religar por telefone, ou remover conscientemente.

`CustomerUser` guarda o `uuid` do Customer. Quando os clientes são recriados
(reset de base, migração), os uuids mudam e o login antigo passa a apontar para
o vazio: `user_can_access_order` devolve False para sempre e o cliente perde o
canal em tempo real do acompanhamento sem nenhum aviso — a tela continua
abrindo, só para de atualizar sozinha.
"""
from __future__ import annotations

import uuid as uuid_lib

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from shopman.doorman.models import CustomerUser
from shopman.guestman.models import Customer

pytestmark = pytest.mark.django_db


def _customer(ref: str, phone: str) -> Customer:
    return Customer.objects.create(ref=ref, first_name="Cliente", phone=phone, is_active=True)


def _link(customer_id, *, phone: str | None, username: str) -> CustomerUser:
    user = get_user_model().objects.create_user(username=username)
    return CustomerUser.objects.create(
        user=user,
        customer_id=customer_id,
        metadata={"phone": phone} if phone is not None else {},
    )


class TestRepair:
    def test_relinks_by_phone_when_the_uuid_died(self):
        current = _customer("CLI-900", "+5543990000001")
        orfao = _link(uuid_lib.uuid4(), phone="+5543990000001", username="c900")

        call_command("cleanup_orphan_customer_links", verbosity=0)

        orfao.refresh_from_db()
        assert orfao.customer_id == current.uuid

    def test_leaves_healthy_links_alone(self):
        vivo = _customer("CLI-901", "+5543990000002")
        link = _link(vivo.uuid, phone="+5543990000002", username="c901")

        call_command("cleanup_orphan_customer_links", verbosity=0)

        link.refresh_from_db()
        assert link.customer_id == vivo.uuid

    def test_dry_run_writes_nothing(self):
        _customer("CLI-902", "+5543990000003")
        morto = uuid_lib.uuid4()
        link = _link(morto, phone="+5543990000003", username="c902")

        call_command("cleanup_orphan_customer_links", "--dry-run", verbosity=0)

        link.refresh_from_db()
        assert link.customer_id == morto


class TestUnrepairable:
    def test_keeps_unrepairable_links_by_default(self):
        """Sem telefone não há como religar — mas remover é decisão explícita."""
        link = _link(uuid_lib.uuid4(), phone=None, username="c903")

        call_command("cleanup_orphan_customer_links", verbosity=0)

        assert CustomerUser.objects.filter(pk=link.pk).exists()

    def test_deletes_unrepairable_when_asked(self):
        link = _link(uuid_lib.uuid4(), phone=None, username="c904")

        call_command("cleanup_orphan_customer_links", "--delete-unrepairable", verbosity=0)

        assert not CustomerUser.objects.filter(pk=link.pk).exists()


class TestLinkRecordsPhone:
    def test_new_links_carry_the_phone_so_they_can_be_repaired(self):
        """Sem isto o reparo é impossível: nada liga o login ao cliente novo."""
        from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

        customer = _customer("CLI-905", "+5543990000004")
        user, _ = get_or_create_user_for_customer(customer)

        link = CustomerUser.objects.get(user=user)
        assert link.metadata.get("phone") == "+5543990000004"
