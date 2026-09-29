"""Cancelar o "avise-me" apaga o número de quem pediu, não só carimba a data.

Quem se inscreve pelo "Me avise" não precisa ter conta: o telefone entra em
`StockAlertSubscription.contact_phone` e essa linha passa a ser o ÚNICO registro
que a loja tem dessa pessoa. Ela não aparece em "Excluir conta" — não há conta —
e a limpeza de privacidade só alcança quem casa `customer_ref`.

Até aqui, cancelar carimbava `revoked_at` e deixava o número no banco esperando
os noventa dias da retenção (R07). A saída existia no papel: a mensagem sempre
carregou o link de gerenciamento, e o link sempre soube cancelar. O que faltava
era o cancelamento APAGAR.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from shopman.offerman.models import Product

from shopman.storefront.models import StockAlertSubscription
from shopman.storefront.services import stock_alerts

pytestmark = pytest.mark.django_db

PHONE = "+5543999990123"


@pytest.fixture(autouse=True)
def configured_channel():
    from shopman.shop.models import Channel

    Channel.objects.get_or_create(ref="web", defaults={"name": "Web", "is_active": True})


def _publish(sku: str) -> Product:
    return Product.objects.create(
        sku=sku,
        name="Pão de Teste",
        base_price_q=500,
        is_published=True,
    )


def _sem_conta(sku: str):
    """A inscrição de quem não tem cadastro: só o telefone identifica."""
    sub = stock_alerts.subscribe(sku, phone=PHONE, adult_declared=True)
    assert sub is not None
    assert sub.customer_ref == ""
    assert sub.contact_phone == PHONE
    return sub


def test_cancelar_pelo_link_da_mensagem_apaga_o_telefone():
    """O único caminho de saída de quem não tem conta precisa apagar de fato."""
    _publish("SKU-CANCELA-APAGA")
    sub = _sem_conta("SKU-CANCELA-APAGA")
    alvo_antes = sub.target_key

    outcome = stock_alerts.revoke_by_capability(stock_alerts.management_capability(sub))

    assert outcome is not None
    sub.refresh_from_db()
    assert sub.revoked_at is not None
    assert sub.contact_phone == ""
    # `target_key` é HMAC do telefone: mantê-lo deixaria de pé o fio que liga
    # entre si todas as inscrições da mesma pessoa.
    assert sub.target_key != alvo_antes
    assert sub.target_key == stock_alerts._erased_target_key(sub.ref)


def test_a_prova_de_que_houve_opt_in_e_cancelamento_sobrevive():
    """Apagar a pessoa não pode apagar a evidência de que ela consentiu."""
    _publish("SKU-CANCELA-PROVA")
    sub = _sem_conta("SKU-CANCELA-PROVA")
    disclosure_hash = sub.disclosure_hash
    disclosure_version = sub.disclosure_version

    stock_alerts.revoke_by_capability(stock_alerts.management_capability(sub))

    sub.refresh_from_db()
    assert sub.revocation_evidence_hash
    assert sub.disclosure_hash == disclosure_hash
    assert sub.disclosure_version == disclosure_version
    assert sub.evidence_hash


def test_depois_do_cancelamento_o_numero_nao_esta_em_lugar_nenhum_da_linha():
    """A varredura é pela linha inteira, não por um campo que eu lembrei."""
    _publish("SKU-CANCELA-VARRE")
    sub = _sem_conta("SKU-CANCELA-VARRE")

    stock_alerts.revoke_by_capability(stock_alerts.management_capability(sub))

    linha = StockAlertSubscription.objects.filter(pk=sub.pk).values().get()
    assert PHONE not in "\n".join(str(valor) for valor in linha.values())
    assert not StockAlertSubscription.objects.filter(contact_phone=PHONE).exists()


def test_cancelar_com_dono_tambem_apaga_o_contato_guardado_na_inscricao():
    """A regra é do cancelamento, não da porta por onde ele entrou."""
    _publish("SKU-CANCELA-DONO")
    sub = _sem_conta("SKU-CANCELA-DONO")

    assert stock_alerts.revoke(sub.ref, phone=PHONE) is True

    sub.refresh_from_db()
    assert sub.revoked_at is not None
    assert sub.contact_phone == ""


def test_a_mensagem_do_avise_me_ensina_a_sair_e_diz_o_que_acontece_com_o_numero():
    """A saída só serve se a pessoa souber que ela existe — e o que ela faz."""
    _publish("SKU-CANCELA-MENSAGEM")
    sub = _sem_conta("SKU-CANCELA-MENSAGEM")

    with patch(
        "shopman.shop.notifications.notify",
        return_value=MagicMock(success=True),
    ) as notify:
        stock_alerts._deliver(sub, product_name="Pão de Teste")

    nota = notify.call_args.kwargs["context"]["management_note"]
    assert stock_alerts.management_url(sub) in nota
    assert "cancelar" in nota.lower()
    assert "apagar o seu número" in nota


def test_cancelar_duas_vezes_nao_quebra_nem_ressuscita_o_numero():
    """Idempotência: o segundo clique no link não pode reabrir nada."""
    _publish("SKU-CANCELA-DUAS")
    sub = _sem_conta("SKU-CANCELA-DUAS")
    capability = stock_alerts.management_capability(sub)

    assert stock_alerts.revoke_by_capability(capability) is not None
    # A capacidade só resolve inscrição não revogada: o segundo cancelamento
    # não encontra mais nada, e é assim que ele falha — sem exceção e sem
    # devolver o número para o banco.
    assert stock_alerts.revoke_by_capability(capability) is None

    sub.refresh_from_db()
    assert sub.contact_phone == ""
