"""Exclusão de conta que falha pela metade não pode se declarar concluída.

`anonymize_customer` roda sete etapas independentes, cada uma com seu
`try/except`. A estrutura está certa: uma falha não pode impedir as outras de
apagarem o que conseguem — quanto mais sair, melhor.

O erro era o que vinha depois: a função voltava sem dizer nada, e a API
respondia `{"ok": true}`. O titular ouvia que seus dados tinham sido apagados
enquanto parte deles seguia no banco. Numa obrigação de LGPD, é a pior resposta
possível — pior que o erro, porque fecha o assunto.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from shopman.shop.services.account import AnonymizationIncomplete, anonymize_customer


@pytest.fixture
def cliente(db):
    from shopman.guestman.models import Customer

    return Customer.objects.create(
        ref="CLI-PARCIAL",
        first_name="Ana",
        last_name="Silva",
        phone="+5543999990001",
        email="ana@example.com",
    )


@pytest.mark.django_db
def test_uma_etapa_que_falha_impede_o_sucesso_e_nomeia_a_etapa(cliente):
    with patch(
        "shopman.guestman.services.customer.purge_pii",
        side_effect=RuntimeError("banco fora"),
    ):
        with pytest.raises(AnonymizationIncomplete) as exc:
            anonymize_customer(cliente)

    assert "purgar PII do cadastro" in exc.value.steps


@pytest.mark.django_db
def test_as_OUTRAS_etapas_rodam_mesmo_assim(cliente):
    """A falha de uma não aborta as demais — apagar o que dá continua sendo o certo."""
    with patch(
        "shopman.guestman.services.customer.purge_pii",
        side_effect=RuntimeError("banco fora"),
    ):
        with pytest.raises(AnonymizationIncomplete):
            anonymize_customer(cliente)

    cliente.refresh_from_db()
    assert cliente.first_name == "Anonimizado"
    assert cliente.phone == ""
    assert cliente.is_active is False


@pytest.mark.django_db
def test_a_operacao_e_avisada_com_severidade_critica(cliente):
    """Dado de titular que não saiu do banco é obrigação legal em aberto."""
    with patch(
        "shopman.guestman.services.customer.purge_pii",
        side_effect=RuntimeError("banco fora"),
    ):
        with patch("shopman.shop.services.observability.create_operator_alert") as alerta:
            with pytest.raises(AnonymizationIncomplete):
                anonymize_customer(cliente)

    assert alerta.called, "ninguém foi avisado de que sobrou dado pessoal no banco"
    kwargs = alerta.call_args.kwargs
    assert kwargs["severity"] == "critical"
    assert kwargs["type"] == "account_deletion_incomplete"
    assert cliente.ref in kwargs["message"]


@pytest.mark.django_db
def test_sem_falha_nenhuma_continua_devolvendo_o_recibo(cliente):
    """O caminho feliz não muda: ref original + hash do telefone."""
    ref, phone_hash = anonymize_customer(cliente)

    assert ref == cliente.ref
    assert len(phone_hash) == 12


@pytest.mark.django_db
def test_rodar_de_novo_numa_conta_ja_anonimizada_NAO_e_falha(cliente):
    """Ausência não é falha — e sem esta distinção a reexecução nunca converge.

    Anonimizar é idempotente de propósito: depois de uma falha parcial, o
    operador roda de novo. Na segunda passada metade das coisas já não existe,
    e as etapas que resolvem o titular pelo `ref` levantam exceção de "não
    achei" — `Customer.DoesNotExist` (o cliente ficou inativo) ou
    `CustomerError(CUSTOMER_NOT_FOUND)`.

    Contar isso como falha faria o alerta crítico gritar para sempre sobre um
    trabalho que TERMINOU, e o titular receber 503 numa exclusão já concluída.
    """
    anonymize_customer(cliente)

    # Segunda passada: não pode levantar, e não pode alertar ninguém.
    with patch("shopman.shop.services.observability.create_operator_alert") as alerta:
        ref, phone_hash = anonymize_customer(cliente)

    assert ref == cliente.ref
    assert len(phone_hash) == 12
    assert not alerta.called, "a reexecução de uma exclusão concluída acordou a operação"
