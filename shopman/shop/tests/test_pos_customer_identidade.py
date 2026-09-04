"""O telefone digitado NÃO troca o dono do pedido.

Comanda com o cliente A associado; o operador digita no campo WhatsApp um
telefone que é de B e conclui. Antes disto, o resolve achava um único candidato
(B), devolvia B, e o front sobrescrevia ref/nome/telefone/e-mail do carrinho —
sem erro, sem aviso, sem nada na tela. Se o nome de B fosse placeholder
("Cliente 1234"), o nome de A ainda ia parar no cadastro de B.

A detecção de conflito sempre existiu em ``_resolve_pos_customer``; o que
faltava era o ``customer_ref`` do cliente já associado CHEGAR até ela. Com o ref
viajando, o caso tem dois candidatos (A por ref, B por telefone) e cai no
conflito — que a tela transforma em escolha do operador.

Irmão por CPF: ``test_fiscal_cpf_e_pedido.py::
test_cpf_da_nota_nao_rouba_a_venda_de_quem_ja_foi_identificado``.

E a outra metade: corrigir um contato errado pelo PDV. O merge só preenchia
lacuna, então telefone digitado errado ontem só tinha conserto no Admin.
"""

from __future__ import annotations

import pytest
from shopman.guestman.models import ContactPoint, Customer

from shopman.shop.models import Channel, Shop
from shopman.shop.services.pos import (
    PosCustomerConflict,
    _persist_customer_from_payload,
    resolve_or_create_customer,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def _pdv():
    Shop.objects.create(name="T", brand_name="T")
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})


def _customer(first_name: str, last_name: str, phone: str = "", **extra) -> Customer:
    # O `Customer` já materializa o ContactPoint principal a partir do `phone`.
    return Customer.objects.create(
        ref=Customer.generate_ref(),
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        **extra,
    )


# ── 1 · O BUG: telefone de outro cliente trocava o dono do pedido ────────────


def test_telefone_de_outro_cliente_nao_troca_o_dono_do_pedido(_pdv):
    """O caso do balcão, na íntegra: A na comanda, telefone de B no campo."""
    a = _customer("Ana", "Prado", "+5543999990011")
    b = _customer("Bruno", "Souza", "+5543999990022")

    with pytest.raises(PosCustomerConflict) as excinfo:
        resolve_or_create_customer(
            ref=a.ref,
            name="Ana Prado",
            phone="43999990022",   # o telefone é de B
            operator_username="op",
        )

    conflito = excinfo.value
    assert conflito.field == "customer_phone"
    assert "WhatsApp" in str(conflito)

    # A tela precisa dos DOIS lados nomeados para oferecer a saída de um toque.
    por_ref = {row["ref"]: row for row in conflito.candidates}
    assert set(por_ref) == {a.ref, b.ref}
    assert por_ref[a.ref]["is_current"] is True
    assert por_ref[a.ref]["matched_by"] == ["ref"]
    assert por_ref[b.ref]["is_current"] is False
    assert por_ref[b.ref]["matched_by"] == ["phone"]
    assert por_ref[b.ref]["name"] == "Bruno Souza"


def test_a_recusa_nao_escreve_nada_em_ninguem(_pdv):
    """Agravante do bug: o nome de A ia parar no cadastro placeholder de B."""
    a = _customer("Ana", "Prado", "+5543999990011")
    b = _customer("Cliente", "0022", "+5543999990022")   # nome placeholder

    with pytest.raises(PosCustomerConflict):
        resolve_or_create_customer(
            ref=a.ref, name="Ana Prado", phone="43999990022", operator_username="op",
        )

    b.refresh_from_db()
    a.refresh_from_db()
    assert b.name == "Cliente 0022"          # `_should_refresh_name` não foi alcançado
    assert a.phone == "+5543999990011"       # e A ficou como estava
    assert Customer.objects.count() == 2     # nem cadastro novo nasceu


def test_sem_ref_o_telefone_resolve_normalmente(_pdv):
    """A outra metade: cliente anônimo digitando o próprio telefone.

    Sem ninguém associado, o telefone é a única identidade que existe — e
    ignorá-lo criaria um cadastro duplicado por venda.
    """
    b = _customer("Bruno", "Souza", "+5543999990022")

    resolvido = resolve_or_create_customer(phone="43999990022", operator_username="op")

    assert resolvido["ref"] == b.ref
    assert Customer.objects.count() == 1


def test_o_proprio_telefone_do_cliente_associado_nao_conflita(_pdv):
    """O caminho normal: o telefone no campo é o do próprio cliente da comanda."""
    a = _customer("Ana", "Prado", "+5543999990011")

    resolvido = resolve_or_create_customer(
        ref=a.ref, name="Ana Prado", phone="43999990011", operator_username="op",
    )

    assert resolvido["ref"] == a.ref
    assert resolvido["created"] is False


def test_ref_sozinho_resolve_o_cliente_associado(_pdv):
    """Cliente sem telefone (só nome) continua alcançável pelo ref."""
    a = _customer("Ana", "Prado")

    resolvido = resolve_or_create_customer(ref=a.ref, operator_username="op")

    assert resolvido["ref"] == a.ref


def test_cpf_de_terceiro_tambem_cai_no_conflito_com_o_campo_certo(_pdv):
    """A mesma trava vale para CPF: o campo nomeado é o do documento."""
    a = _customer("Ana", "Prado", "+5543999990011")
    _customer("Bruno", "Souza", "+5543999990022", document="52998224725")

    with pytest.raises(PosCustomerConflict) as excinfo:
        resolve_or_create_customer(ref=a.ref, tax_id="52998224725", operator_username="op")

    assert excinfo.value.field == "customer_tax_id"
    assert "CPF/CNPJ" in str(excinfo.value)


def test_dois_intrusos_por_campos_diferentes_caem_na_frase_generica(_pdv):
    """Sem UM campo culpado, a tela não pode nomear um — e o texto assume isso."""
    a = _customer("Ana", "Prado", "+5543999990011")
    _customer("Bruno", "Souza", "+5543999990022")
    _customer("Célia", "Dias", "+5543999990033", document="52998224725")

    with pytest.raises(PosCustomerConflict) as excinfo:
        resolve_or_create_customer(
            ref=a.ref, phone="43999990022", tax_id="52998224725", operator_username="op",
        )

    assert excinfo.value.field == ""
    assert "cadastros diferentes" in str(excinfo.value)
    assert len(excinfo.value.candidates) == 3


def test_o_conflito_continua_valendo_no_commit_da_venda(_pdv):
    """A comanda salva carrega `customer_ref`: fechar a venda não fura a trava."""
    a = _customer("Ana", "Prado", "+5543999990011")
    _customer("Bruno", "Souza", "+5543999990022")

    with pytest.raises(PosCustomerConflict):
        _persist_customer_from_payload(
            {"customer_ref": a.ref, "customer_phone": "43999990022"},
            operator_username="op",
        )


# ── 4 · CORRIGIR o contato pelo PDV, com a palavra do operador ───────────────


def test_sem_a_palavra_do_operador_o_telefone_certo_nao_e_reescrito(_pdv):
    """A regra velha continua de pé: campo preenchido não muda por inércia."""
    a = _customer("Ana", "Prado", "+5543999990011")

    resolve_or_create_customer(
        ref=a.ref, name="Ana Prado", phone="43988887777", operator_username="op",
    )

    a.refresh_from_db()
    assert a.phone == "+5543999990011"


def test_com_a_palavra_do_operador_o_telefone_errado_tem_conserto(_pdv):
    """O número novo vira o PRINCIPAL, e o cache do cadastro acompanha."""
    a = _customer("Ana", "Prado", "+5543999990011")

    resolvido = resolve_or_create_customer(
        ref=a.ref,
        name="Ana Prado",
        phone="43988887777",
        contact_correction=True,
        operator_username="op",
    )

    a.refresh_from_db()
    assert resolvido["ref"] == a.ref
    assert a.phone == "+5543988887777"
    novo = ContactPoint.objects.get(customer=a, value_normalized="+5543988887777")
    assert novo.is_primary is True
    # O antigo fica no histórico, demovido — não sai apagando contato de ninguém.
    antigo = ContactPoint.objects.get(customer=a, value_normalized="+5543999990011")
    assert antigo.is_primary is False


def test_a_correcao_recusa_quando_o_numero_novo_ja_e_de_terceiro(_pdv):
    """Corrigir não é roubar: o conflito vem ANTES, com a mesma gêmea na tela."""
    a = _customer("Ana", "Prado", "+5543999990011")
    b = _customer("Bruno", "Souza", "+5543999990022")

    with pytest.raises(PosCustomerConflict):
        resolve_or_create_customer(
            ref=a.ref, phone="43999990022", contact_correction=True, operator_username="op",
        )

    a.refresh_from_db()
    b.refresh_from_db()
    assert a.phone == "+5543999990011"
    assert b.phone == "+5543999990022"


def test_a_correcao_so_vale_para_o_cadastro_que_o_ref_apontou(_pdv):
    """Sem ref não há 'de quem' corrigir — e o resolve por telefone não vira porta."""
    b = _customer("Bruno", "Souza", "+5543999990022")

    resolve_or_create_customer(
        phone="43999990022",
        email="bruno@example.com",
        contact_correction=True,   # sem ref: a correção não se aplica
        operator_username="op",
    )

    b.refresh_from_db()
    assert b.email == "bruno@example.com"   # lacuna, isso o merge sempre fez


def test_a_correcao_nao_toca_no_documento_fiscal(_pdv):
    """O CPF pedido nesta venda pode ser o do marido: nunca é correção de identidade."""
    a = _customer("Ana", "Prado", "+5543999990011", document="52998224725")

    resolve_or_create_customer(
        ref=a.ref,
        phone="43988887777",
        tax_id="11144477735",
        contact_correction=True,
        operator_username="op",
    )

    a.refresh_from_db()
    assert a.phone == "+5543988887777"     # contato corrigiu
    assert a.document == "52998224725"     # documento NÃO


def test_a_correcao_troca_o_email_do_cadastro(_pdv):
    a = _customer("Ana", "Prado", "+5543999990011", email="antigo@example.com")

    resolve_or_create_customer(
        ref=a.ref, email="novo@example.com", contact_correction=True, operator_username="op",
    )

    a.refresh_from_db()
    assert a.email == "novo@example.com"
