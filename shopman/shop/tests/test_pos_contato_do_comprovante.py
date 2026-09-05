"""O contato do comprovante vira cadastro quando PERGUNTAM — e só então.

O crime nunca foi gravar. O crime era gravar CALADO: o e-mail digitado para
receber a nota virava ``customer.email`` sem que ninguém dissesse nada, e o CPF
pedido na nota entrava no cadastro pela mesma porta muda. Quando o valor já era
de outra pessoa, o UNIQUE global recusava com ``IntegrityError``, a view não
sabia lê-lo, e o balcão via HTTP 500 com a venda travada.

A metade defensiva cortou o vazamento. Esta é a metade generosa: a tela
PERGUNTA, e a resposta viaja como ordem explícita (``save_receipt_contact`` /
``save_receipt_tax_id``). A matriz, igual para e-mail e para CPF:

    cliente sem o contato       → oferece salvar        (grava quando mandam)
    cliente com o MESMO contato → nada a perguntar      (no-op)
    cliente com contato DIVERSO → cadastro INTACTO      (atualizar é ação à parte)
    contato de OUTRO cadastro   → conflito rico, 422    (nunca 500)
    sem cliente identificado    → "salvar como cliente?" (nasce quando mandam)
"""

from __future__ import annotations

import pytest

from shopman.shop.services.pos import PosCustomerConflict, _persist_customer_from_payload

pytestmark = pytest.mark.django_db

CPF_A = "52998224725"
CPF_B = "11144477735"


@pytest.fixture(autouse=True)
def _loja():
    from shopman.shop.models import Channel, Shop

    Shop.objects.create(name="T", brand_name="T")
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})


def _cliente(**kwargs):
    from shopman.guestman.models import Customer

    kwargs.setdefault("first_name", "Fulano")
    kwargs.setdefault("last_name", "Silva")
    return Customer.objects.create(ref=Customer.generate_ref(), **kwargs)


def _salvar(payload):
    return _persist_customer_from_payload(payload, operator_username="op")


# ── Linha 1: cliente identificado, SEM o contato no cadastro ──────────────


def test_email_do_comprovante_entra_no_cadastro_vazio_quando_mandam():
    cliente = _cliente(phone="+5543999990001")

    _salvar({
        "customer_ref": cliente.ref,
        "receipt_channels": ["email"],
        "receipt_email": "ana@example.org",
        "save_receipt_contact": True,
    })

    cliente.refresh_from_db()
    assert cliente.email == "ana@example.org"


def test_email_do_comprovante_NAO_entra_no_cadastro_vazio_sem_a_ordem():
    cliente = _cliente(phone="+5543999990002")

    _salvar({
        "customer_ref": cliente.ref,
        "receipt_channels": ["email"],
        "receipt_email": "ana@example.org",
    })

    cliente.refresh_from_db()
    assert cliente.email == ""


def test_cpf_da_nota_entra_no_cadastro_vazio_quando_mandam():
    cliente = _cliente(phone="+5543999990003")

    _salvar({"customer_ref": cliente.ref, "fiscal_tax_id": CPF_A, "save_receipt_tax_id": True})

    cliente.refresh_from_db()
    assert cliente.document == CPF_A


def test_cpf_da_nota_NAO_entra_no_cadastro_vazio_sem_a_ordem():
    cliente = _cliente(phone="+5543999990004")

    _salvar({"customer_ref": cliente.ref, "fiscal_tax_id": CPF_A})

    cliente.refresh_from_db()
    assert cliente.document == ""


# ── Linha 2: contato IGUAL ao do cadastro — nada a perguntar ──────────────


def test_email_igual_ao_do_cadastro_nao_muda_nada():
    cliente = _cliente(phone="+5543999990005", email="ana@example.org")

    _salvar({
        "customer_ref": cliente.ref,
        "receipt_channels": ["email"],
        "receipt_email": "ana@example.org",
        "save_receipt_contact": True,
    })

    cliente.refresh_from_db()
    assert cliente.email == "ana@example.org"


def test_cpf_igual_ao_do_cadastro_nao_muda_nada():
    cliente = _cliente(phone="+5543999990006", document=CPF_A)

    _salvar({"customer_ref": cliente.ref, "fiscal_tax_id": CPF_A, "save_receipt_tax_id": True})

    cliente.refresh_from_db()
    assert cliente.document == CPF_A


# ── Linha 3: contato DIFERENTE — cadastro intacto por padrão ──────────────


def test_email_diferente_deixa_o_cadastro_INTACTO_e_a_nota_vai_para_o_informado():
    """O caso que o dono fez questão de marcar: a nota para o contador.

    Sem ordem, ``customer.email`` não se mexe — e o endereço da nota continua
    sendo o digitado, porque ele vive em ``receipt.email``, fato da venda.
    """
    from shopman.shop.services.pos import build_session_ops

    cliente = _cliente(phone="+5543999990007", email="ana@example.org")

    ops = build_session_ops(
        {
            "customer_ref": cliente.ref,
            "items": [],
            "receipt_channels": ["email"],
            "receipt_email": "contador@example.org",
        },
        "op",
    )

    cliente.refresh_from_db()
    assert cliente.email == "ana@example.org"
    assert {"op": "set_data", "path": "receipt.email", "value": "contador@example.org"} in ops


def test_email_diferente_SO_e_atualizado_com_a_ordem_nomeada():
    cliente = _cliente(phone="+5543999990008", email="ana@example.org")

    _salvar({
        "customer_ref": cliente.ref,
        "receipt_channels": ["email"],
        "receipt_email": "ana.nova@example.org",
        "save_receipt_contact": True,
    })

    cliente.refresh_from_db()
    assert cliente.email == "ana.nova@example.org"


def test_cpf_diferente_deixa_o_cadastro_INTACTO():
    cliente = _cliente(phone="+5543999990009", document=CPF_A)

    _salvar({"customer_ref": cliente.ref, "fiscal_tax_id": CPF_B})

    cliente.refresh_from_db()
    assert cliente.document == CPF_A


def test_cpf_diferente_SO_e_atualizado_com_a_ordem_nomeada():
    cliente = _cliente(phone="+5543999990010", document=CPF_A)

    _salvar({"customer_ref": cliente.ref, "fiscal_tax_id": CPF_B, "save_receipt_tax_id": True})

    cliente.refresh_from_db()
    assert cliente.document == CPF_B


def test_corrigir_contato_NAO_arrasta_o_documento_junto():
    """A ordem sobre o telefone não é ordem sobre o CPF.

    ``customer_contact_correction`` conserta o contato digitado errado; deixar
    o documento pegar carona nela seria o mesmo gravar-calado de sempre.
    """
    cliente = _cliente(phone="+5543999990011", document=CPF_A)

    _salvar({
        "customer_ref": cliente.ref,
        "customer_phone": "43999998888",
        "fiscal_tax_id": CPF_B,
        "customer_contact_correction": True,
    })

    cliente.refresh_from_db()
    assert cliente.phone == "+5543999998888"
    assert cliente.document == CPF_A


def test_salvar_o_email_do_comprovante_NAO_troca_o_telefone_do_cadastro():
    """Mandar guardar o e-mail não é autorização para mexer no WhatsApp."""
    cliente = _cliente(phone="+5543999990012", email="ana@example.org")

    _salvar({
        "customer_ref": cliente.ref,
        "customer_phone": "43999997777",
        "receipt_channels": ["email"],
        "receipt_email": "ana.nova@example.org",
        "save_receipt_contact": True,
    })

    cliente.refresh_from_db()
    assert cliente.phone == "+5543999990012"
    assert cliente.email == "ana.nova@example.org"


# ── Linha 4: o contato é de OUTRO cadastro → conflito rico, nunca 500 ──────


def test_email_de_outro_cadastro_vira_conflito_RICO_e_nao_IntegrityError():
    cliente = _cliente(phone="+5543999990013")
    outro = _cliente(first_name="Bia", phone="+5543999990014", email="bia@example.org")

    with pytest.raises(PosCustomerConflict) as excinfo:
        _salvar({
            "customer_ref": cliente.ref,
            "receipt_channels": ["email"],
            "receipt_email": "bia@example.org",
            "save_receipt_contact": True,
        })

    conflito = excinfo.value
    assert conflito.field == "customer_email"
    assert {row["ref"] for row in conflito.candidates} == {cliente.ref, outro.ref}
    assert any(row["is_current"] for row in conflito.candidates)


def test_cpf_de_outro_cadastro_vira_conflito_RICO_e_nao_IntegrityError():
    cliente = _cliente(phone="+5543999990015")
    outro = _cliente(first_name="Bia", phone="+5543999990016", document=CPF_A)

    with pytest.raises(PosCustomerConflict) as excinfo:
        _salvar({
            "customer_ref": cliente.ref,
            "fiscal_tax_id": CPF_A,
            "save_receipt_tax_id": True,
        })

    conflito = excinfo.value
    assert conflito.field == "customer_tax_id"
    assert {row["ref"] for row in conflito.candidates} == {cliente.ref, outro.ref}


def test_dono_DESATIVADO_do_email_tambem_sai_nomeado():
    """O caso que a busca não enxerga e o banco enxerga.

    O cadastro desativado segura o endereço no UNIQUE global; sem nomeá-lo, o
    operador lia "já é de outro cadastro" e procurava alguém invisível.
    """
    cliente = _cliente(phone="+5543999990017")
    _cliente(first_name="Bia", phone="+5543999990018", email="bia@example.org", is_active=False)

    with pytest.raises(PosCustomerConflict) as excinfo:
        _salvar({
            "customer_ref": cliente.ref,
            "receipt_channels": ["email"],
            "receipt_email": "bia@example.org",
            "save_receipt_contact": True,
        })

    assert any(row["owner_inactive"] for row in excinfo.value.candidates)


def test_sem_a_ordem_o_email_de_outro_cadastro_nem_e_olhado():
    """A nota vai para o endereço de outro cliente sem conflito nenhum.

    É o pedido do dono: "a pessoa pode querer enviar para outro e-mail". Sem
    ordem de gravar, ninguém disputa a posse de nada.
    """
    cliente = _cliente(phone="+5543999990019")
    _cliente(first_name="Bia", phone="+5543999990020", email="bia@example.org")

    resolvido = _salvar({
        "customer_ref": cliente.ref,
        "receipt_channels": ["email"],
        "receipt_email": "bia@example.org",
    })

    assert resolvido["ref"] == cliente.ref


# ── Linha 5: SEM cliente identificado → "Salvar como cliente?" ────────────


def test_sem_cliente_identificado_marcado_faz_o_cadastro_NASCER():
    from shopman.guestman.models import Customer

    resolvido = _salvar({
        "receipt_channels": ["email"],
        "receipt_email": "novo@example.org",
        "save_receipt_contact": True,
    })

    assert resolvido["created"] is True
    assert Customer.objects.get(ref=resolvido["ref"]).email == "novo@example.org"


def test_sem_cliente_identificado_desmarcado_NAO_cria_cadastro():
    from shopman.guestman.models import Customer

    resolvido = _salvar({"receipt_channels": ["email"], "receipt_email": "novo@example.org"})

    assert resolvido == {}
    assert Customer.objects.count() == 0


def test_sem_cliente_identificado_o_cpf_marcado_faz_o_cadastro_NASCER():
    from shopman.guestman.models import Customer

    resolvido = _salvar({"fiscal_tax_id": CPF_A, "save_receipt_tax_id": True})

    assert resolvido["created"] is True
    assert Customer.objects.get(ref=resolvido["ref"]).document == CPF_A


def test_sem_cliente_identificado_o_cpf_desmarcado_NAO_cria_cadastro():
    from shopman.guestman.models import Customer

    resolvido = _salvar({"fiscal_tax_id": CPF_A})

    assert resolvido == {}
    assert Customer.objects.count() == 0


def test_salvar_como_cliente_ACHA_quem_ja_existe_em_vez_de_duplicar():
    from shopman.guestman.models import Customer

    ja_existe = _cliente(first_name="Bia", phone="+5543999990021", email="bia@example.org")

    resolvido = _salvar({
        "receipt_channels": ["email"],
        "receipt_email": "bia@example.org",
        "save_receipt_contact": True,
    })

    assert resolvido["ref"] == ja_existe.ref
    assert resolvido["created"] is False
    assert Customer.objects.count() == 1


def test_a_venda_fecha_igual_com_a_oferta_desmarcada():
    """Desmarcar não pode custar a venda: as ops do pedido saem iguais."""
    from shopman.shop.services.pos import build_session_ops

    base = {
        "items": [],
        "receipt_channels": ["email"],
        "receipt_email": "novo@example.org",
        "fiscal_tax_id": CPF_A,
    }
    ops = build_session_ops(dict(base), "op")

    assert {"op": "set_data", "path": "receipt.email", "value": "novo@example.org"} in ops
    assert {"op": "set_data", "path": "fiscal.tax_id", "value": CPF_A} in ops
    assert not any(op.get("path") == "customer.ref" for op in ops)
