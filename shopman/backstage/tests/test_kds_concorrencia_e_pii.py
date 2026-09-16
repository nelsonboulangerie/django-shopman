"""Dois tablets na mesma bancada, e uma TV no salão.

Os dois achados aqui têm o mesmo formato: o código promete uma coisa no docstring e
faz outra, e o teste que existia passava por rodar num mundo simples demais.

- **O item desmarcava sozinho.** "Marcar item" recebia um estado DESEJADO e o serviço
  lia o estado atual FORA do lock para decidir se mudava. O `select_for_update`
  protegia só a inversão. O teste chamado "idempotent" passava porque roda em série.
- **O painel público mostrava o telefone.** `_public_comanda_code` promete no docstring
  que protege, e tratava ``isdigit()`` como sinônimo de "não identificante". O
  assert-negativo de PII que existia testa NOME, não dígito.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from shopman.orderman.models import Session

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.projections.kds import _public_comanda_code
from shopman.backstage.services import kds as kds_service


@pytest.fixture
def ticket(db):
    estacao = KDSInstance.objects.create(ref="prep-conc", name="Preparo", type="prep")
    return KDSTicket.objects.create(
        session_key="sk-conc-1",
        kds_instance=estacao,
        items=[
            {"sku": "PAO", "name": "Pão", "qty": 1, "checked": False},
            {"sku": "CAFE", "name": "Café", "qty": 1, "checked": False},
        ],
    )


# ── O item que desmarcava sozinho ────────────────────────────────────────────
#
# ⚠️ Os dois primeiros testes desta seção são os que DISCRIMINAM o conserto. Um
# teste "marcar duas vezes deixa marcado", em série, PASSA com o toggle — porque a
# comparação pré-lock pula a segunda chamada. Foi assim que o teste chamado
# "idempotent" viveu ao lado do bug. Provar de verdade exige atacar as duas metades
# separadamente: o núcleo escreve o desejado, e o serviço não decide antes.


@pytest.mark.django_db
def test_o_NUCLEO_escreve_o_estado_desejado_sem_olhar_o_anterior(ticket):
    """O discriminador do lado do core: `set`, não `toggle`.

    Com `toggle`, esta mesma chamada — item JÁ marcado, comando "marcar" — inverte
    para desmarcado. É esse comportamento que, sob dois tablets, fazia o pão que o
    cozinheiro acabou de marcar desmarcar sozinho.
    """
    from shopman.shop.services import kds as kds_core

    kds_core.set_ticket_item_checked(ticket, index=0, checked=True, actor="joyce")
    ticket.refresh_from_db()
    assert ticket.items[0]["checked"] is True

    # De novo, com o MESMO estado desejado, direto no core — sem o serviço no meio.
    kds_core.set_ticket_item_checked(ticket, index=0, checked=True, actor="bia")

    ticket.refresh_from_db()
    assert ticket.items[0]["checked"] is True, "o núcleo inverteu em vez de escrever"


@pytest.mark.django_db
def test_o_SERVICO_nao_decide_antes_de_travar(ticket, monkeypatch):
    """O discriminador do lado do serviço: a leitura pré-lock SUMIU.

    Enquanto existisse um "se o atual já é o desejado, não faz nada", a corrida
    voltaria — esse dado envelhece entre ler e travar, e é exatamente ali que a
    outra requisição escreve. A prova é que o núcleo é chamado MESMO quando o estado
    atual já é o desejado.
    """
    from shopman.shop.services import kds as kds_core

    kds_service.set_ticket_item_checked(ticket_pk=ticket.pk, index=0, checked=True, actor="joyce")

    chamadas = []
    real = kds_core.set_ticket_item_checked

    def espiao(*args, **kwargs):
        chamadas.append(kwargs.get("checked"))
        return real(*args, **kwargs)

    monkeypatch.setattr(kds_service.kds_core, "set_ticket_item_checked", espiao)

    # Estado atual JÁ é `True`; o comando pede `True` de novo.
    kds_service.set_ticket_item_checked(ticket_pk=ticket.pk, index=0, checked=True, actor="bia")

    assert chamadas == [True], (
        "o serviço voltou a comparar antes de travar — a corrida volta com ela"
    )


@pytest.mark.django_db
def test_marcar_duas_vezes_deixa_marcado(ticket):
    """Guarda de comportamento (passa no main também — não é o discriminador)."""
    kds_service.set_ticket_item_checked(ticket_pk=ticket.pk, index=0, checked=True, actor="joyce")
    kds_service.set_ticket_item_checked(ticket_pk=ticket.pk, index=0, checked=True, actor="bia")

    ticket.refresh_from_db()
    assert ticket.items[0]["checked"] is True


@pytest.mark.django_db
def test_desmarcar_duas_vezes_deixa_desmarcado(ticket):
    """O simétrico. Também guarda de comportamento, não prova da corrida."""
    kds_service.set_ticket_item_checked(ticket_pk=ticket.pk, index=0, checked=True, actor="joyce")

    kds_service.set_ticket_item_checked(ticket_pk=ticket.pk, index=0, checked=False, actor="joyce")
    kds_service.set_ticket_item_checked(ticket_pk=ticket.pk, index=0, checked=False, actor="bia")

    ticket.refresh_from_db()
    assert ticket.items[0]["checked"] is False


@pytest.mark.django_db
def test_marcar_um_item_nao_toca_o_vizinho(ticket):
    kds_service.set_ticket_item_checked(ticket_pk=ticket.pk, index=0, checked=True, actor="joyce")

    ticket.refresh_from_db()
    assert ticket.items[0]["checked"] is True
    assert ticket.items[1]["checked"] is False


@pytest.mark.django_db
def test_marcar_um_item_poe_o_ticket_em_preparo(ticket):
    """O efeito que o `set` não pode ter perdido junto com o toggle."""
    assert ticket.status == "pending"

    kds_service.set_ticket_item_checked(ticket_pk=ticket.pk, index=0, checked=True, actor="joyce")

    ticket.refresh_from_db()
    assert ticket.status == "in_progress"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status", "command"),
    [
        ("pending", "check"),
        ("pending", "complete"),
        ("done", "recall"),
        ("cancelled", "ack"),
    ],
)
def test_todo_writer_do_kds_trava_a_fonte_antes_do_ticket(
    ticket, monkeypatch, status, command
):
    """Guarda estrutural contra reintroduzir ``KDSTicket -> Session/Order``."""
    from shopman.shop.services import kds as kds_core

    Session.objects.create(
        session_key=ticket.session_key,
        channel_ref="pdv",
        state="open",
    )
    ticket.status = status
    ticket.save(update_fields=["status"])

    calls = []
    real_source = kds_core._lock_source_for_session
    real_ticket = kds_core._lock_ticket_after_source

    def source_lock(session_key):
        calls.append("source")
        return real_source(session_key)

    def ticket_lock(current):
        calls.append("ticket")
        return real_ticket(current)

    monkeypatch.setattr(kds_core, "_lock_source_for_session", source_lock)
    monkeypatch.setattr(kds_core, "_lock_ticket_after_source", ticket_lock)

    if command == "check":
        kds_core.set_ticket_item_checked(ticket, index=0, checked=True, actor="kds:test")
    elif command == "complete":
        kds_core.complete_ticket(ticket, actor="kds:test")
    elif command == "recall":
        kds_core.reopen_ticket(ticket, actor="kds:test")
    else:
        kds_core.acknowledge_ticket(ticket, actor="kds:test")

    assert calls[:2] == ["source", "ticket"]


@pytest.mark.django_db
@pytest.mark.parametrize("command", ["unfire", "cancel"])
def test_writer_do_pdv_tambem_usa_fonte_antes_do_ledger_de_tickets(
    ticket, monkeypatch, command
):
    from shopman.shop.adapters import kds as kds_adapter
    from shopman.shop.services import kds as kds_core

    Session.objects.create(
        session_key=ticket.session_key,
        channel_ref="pdv",
        state="open",
    )
    ticket.items[0]["line_id"] = "linha-1"
    ticket.save(update_fields=["items"])

    calls = []
    real_source = kds_core._lock_source_for_session
    adapter_name = (
        "unfire_session_lines" if command == "unfire" else "cancel_open_tickets_for_session"
    )
    real_writer = getattr(kds_adapter, adapter_name)

    def source_lock(session_key):
        calls.append("source")
        return real_source(session_key)

    def ticket_writer(*args, **kwargs):
        calls.append("ticket")
        return real_writer(*args, **kwargs)

    monkeypatch.setattr(kds_core, "_lock_source_for_session", source_lock)
    monkeypatch.setattr(kds_adapter, adapter_name, ticket_writer)

    if command == "unfire":
        kds_core.unfire_lines(session_key=ticket.session_key, line_ids=["linha-1"])
    else:
        kds_core.cancel_tickets_for_session(ticket.session_key)

    assert calls[:2] == ["source", "ticket"]


# ── A TV do salão ────────────────────────────────────────────────────────────


def _sessao(tab_ref: str) -> Session:
    return Session(session_key="sk-pub-1", data={"tab_ref": tab_ref})


@pytest.mark.django_db
@pytest.mark.parametrize("identificador", ["43999887766", "12345678901", "04345678901"])
def test_telefone_e_cpf_nao_vao_para_a_TV(identificador):
    """11 dígitos é `isdigit()` e NÃO é comanda — a diferença vazava o cliente.

    O caminho do operador é banal: o balcão abre a comanda com o telefone do cliente,
    que é o identificador que ele já pediu para o WhatsApp. Ia inteiro para a tela do
    salão, em fonte de 7rem.
    """
    codigo = _public_comanda_code(_sessao(identificador))

    assert identificador not in codigo
    assert codigo.startswith("#"), f"deveria cair no hash, veio {codigo!r}"


@pytest.mark.django_db
@pytest.mark.parametrize(("tab_ref", "esperado"), [("1012", "1012"), ("00001012", "1012"), ("7", "7")])
def test_a_comanda_de_verdade_continua_aparecendo(tab_ref, esperado):
    """Assert-positivo: proteger não pode custar a função da tela.

    O cliente precisa reconhecer o próprio número; se tudo virasse hash, a TV
    deixaria de servir para o que existe.
    """
    assert _public_comanda_code(_sessao(tab_ref)) == esperado


@pytest.mark.django_db
def test_nome_continua_virando_codigo(client):
    """O caso que o assert-negativo antigo já cobria — que não pode ter regredido."""
    codigo = _public_comanda_code(_sessao("João"))

    assert "João" not in codigo
    assert codigo.startswith("#")


@pytest.mark.django_db
def test_o_codigo_e_estavel_entre_atualizacoes_do_painel():
    """O painel recarrega a cada 10s: um código que dança não serve para chamar ninguém."""
    primeiro = _public_comanda_code(_sessao("43999887766"))
    segundo = _public_comanda_code(_sessao("43999887766"))

    assert primeiro == segundo


@pytest.mark.django_db
def test_o_painel_publico_nao_publica_digito_de_cliente(client, db):
    """Ponta a ponta, pela API pública — não pelo helper.

    É a diferença entre provar a função e provar a TELA.
    """
    KDSInstance.objects.create(ref="exp-pub", name="Expedição", type="expedition")
    # Comanda de PDV já enviada à cozinha e ainda não paga — é este caminho
    # (`state="open"` + `fired_lines`) que a projection publica pelo código público.
    Session.objects.create(
        session_key="sk-pub-e2e",
        channel_ref="pdv",
        state="open",
        data={"tab_ref": "43999887766", "fired_lines": ["1"], "fulfillment_type": "pickup"},
    )

    corpo = client.get(reverse("api-backstage-kds-customer")).content.decode()

    assert "43999887766" not in corpo
