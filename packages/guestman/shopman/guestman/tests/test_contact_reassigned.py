"""Número que muda de dono não leva a conta junto (D3, OC-07).

O Guestman é o dono da posse do contato: ele avisa, num lugar só
(``contact_reassigned``), quando um número deixou de ser de um cadastro, e o
identificador do assinante do WhatsApp sai junto. O ``sync_subscriber`` não
reencontra o cadastro antigo pelo assinante quando o número que ele traz já não
é desse cadastro.
"""

from __future__ import annotations

import pytest
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.contrib.manychat.service import ManychatService
from shopman.guestman.models import ContactPoint, Customer
from shopman.guestman.services import identity
from shopman.guestman.signals import contact_reassigned

pytestmark = pytest.mark.django_db

NUMERO = "+5543999991001"
NUMERO_NOVO = "+5543999991002"
ASSINANTE = "880001"


@pytest.fixture
def avisos():
    recebidos: list[dict] = []

    def _receiver(sender, **kwargs):
        recebidos.append(kwargs)

    contact_reassigned.connect(_receiver, dispatch_uid="test_contact_reassigned_avisos")
    yield recebidos
    contact_reassigned.disconnect(dispatch_uid="test_contact_reassigned_avisos")


def _anterior() -> Customer:
    """A pessoa que tinha o número: entrou pelo WhatsApp (assinante 880001)."""
    customer, created = ManychatService.sync_subscriber(
        {"id": ASSINANTE, "first_name": "Ana", "whatsapp_id": NUMERO}
    )
    assert created
    return customer


def _chaves(customer) -> set[tuple[str, str]]:
    return set(
        CustomerIdentifier.objects.filter(customer=customer).values_list(
            "identifier_type", "identifier_value"
        )
    )


def test_numero_que_sai_avisa_com_o_assinante(avisos):
    ana = _anterior()

    ContactPoint.objects.filter(customer=ana, value_normalized=NUMERO).delete()

    assert avisos, "o número saiu e ninguém soube"
    # Telefone e WhatsApp do mesmo número saem no mesmo delete: o aviso pode vir por
    # linha, e quem escuta é idempotente. O que importa é o conteúdo.
    assert {(aviso["customer_id"], aviso["value"]) for aviso in avisos} == {(ana.pk, NUMERO)}
    aviso = avisos[-1]
    assert aviso["customer_id"] == ana.pk
    assert aviso["customer_ref"] == ana.ref
    assert aviso["value"] == NUMERO
    assert aviso["verification_ref"] == ASSINANTE
    assert aviso["source"] == identity.SOURCE_CONTACT_REMOVED


def test_o_assinante_do_whatsapp_sai_junto_com_o_numero():
    ana = _anterior()
    assert (IdentifierType.MANYCHAT, ASSINANTE) in _chaves(ana)

    ContactPoint.objects.filter(customer=ana, value_normalized=NUMERO).delete()

    assert _chaves(ana) == set()


def test_apagar_so_o_contato_de_voz_nao_e_perder_o_numero(avisos):
    ana = _anterior()

    ContactPoint.objects.filter(customer=ana, type=ContactPoint.Type.PHONE).delete()

    assert avisos == []
    assert (IdentifierType.MANYCHAT, ASSINANTE) in _chaves(ana)


def test_trocar_o_proprio_numero_solta_o_assinante_do_numero_antigo(avisos):
    ana = _anterior()

    identity.replace_primary_contact(ana, field="phone", new_value=NUMERO_NOVO)

    assert {aviso["value"] for aviso in avisos} == {NUMERO}
    assert (IdentifierType.MANYCHAT, ASSINANTE) not in _chaves(ana)


def test_quem_herda_o_numero_nasce_cadastro_proprio_pelo_whatsapp():
    """O caso S3 do laudo: o assinante sobrevive à troca e reencontrava a conta antiga."""
    ana = _anterior()
    identity.replace_primary_contact(ana, field="phone", new_value=NUMERO_NOVO)

    herdeiro, created = ManychatService.sync_subscriber(
        {"id": ASSINANTE, "first_name": "Bruno", "whatsapp_id": NUMERO}
    )

    assert created
    assert herdeiro.pk != ana.pk
    ana.refresh_from_db()
    assert ana.phone == NUMERO_NOVO
    assert not ContactPoint.objects.filter(customer=ana, value_normalized=NUMERO).exists()


def test_assinante_antigo_preso_ao_cadastro_e_cortado_na_porta(avisos):
    """Identificador que sobrou de antes (sem o contato): a sincronização corta e avisa."""
    ana = Customer.objects.create(ref="CUS-REA-01", first_name="Ana", phone=NUMERO_NOVO)
    ContactPoint.objects.create(
        customer=ana, type=ContactPoint.Type.WHATSAPP, value_normalized=NUMERO_NOVO, is_primary=True
    )
    CustomerIdentifier.objects.create(
        customer=ana,
        identifier_type=IdentifierType.MANYCHAT,
        identifier_value=ASSINANTE,
        source_system="manychat",
    )

    herdeiro, created = ManychatService.sync_subscriber(
        {"id": ASSINANTE, "first_name": "Bruno", "whatsapp_id": NUMERO}
    )

    assert created and herdeiro.pk != ana.pk
    assert (IdentifierType.MANYCHAT, ASSINANTE) not in _chaves(ana)
    assert (IdentifierType.MANYCHAT, ASSINANTE) in _chaves(herdeiro)
    assert [(aviso["customer_id"], aviso["source"]) for aviso in avisos] == [
        (ana.pk, identity.SOURCE_PROVIDER_SUBSCRIBER_MOVED)
    ]


def test_cadastro_sem_numero_recebe_o_numero_do_assinante_como_sempre():
    ana = Customer.objects.create(ref="CUS-REA-02", first_name="Ana")
    CustomerIdentifier.objects.create(
        customer=ana,
        identifier_type=IdentifierType.MANYCHAT,
        identifier_value=ASSINANTE,
        source_system="manychat",
    )

    mesma, created = ManychatService.sync_subscriber({"id": ASSINANTE, "whatsapp_id": NUMERO})

    assert not created and mesma.pk == ana.pk
    assert mesma.phone == NUMERO


def test_mesmo_numero_segue_achando_a_mesma_pessoa():
    ana = _anterior()

    mesma, created = ManychatService.sync_subscriber({"id": ASSINANTE, "whatsapp_id": NUMERO})

    assert not created and mesma.pk == ana.pk


def test_sinal_de_troca_de_dono_tira_o_numero_e_avisa_com_a_origem(avisos):
    ana = _anterior()

    refs = identity.release_reassigned_contact(NUMERO, source="camara_number_recycling")

    assert refs == [ana.ref]
    ana.refresh_from_db()
    assert ana.phone == ""
    assert not ContactPoint.objects.filter(value_normalized=NUMERO).exists()
    assert _chaves(ana) == set()
    assert [(aviso["value"], aviso["source"]) for aviso in avisos] == [(NUMERO, "camara_number_recycling")]


def test_sinal_para_numero_sem_dono_nao_faz_nada(avisos):
    assert identity.release_reassigned_contact(NUMERO, source="camara_number_recycling") == []
    assert avisos == []


def test_numero_so_no_cache_tambem_sai_e_avisa(avisos):
    ana = Customer.objects.create(ref="CUS-REA-03", first_name="Ana")
    Customer.objects.filter(pk=ana.pk).update(phone=NUMERO)

    assert identity.release_reassigned_contact(NUMERO, source="customer_not_me") == [ana.ref]

    ana.refresh_from_db()
    assert ana.phone == ""
    assert [aviso["customer_id"] for aviso in avisos] == [ana.pk]
