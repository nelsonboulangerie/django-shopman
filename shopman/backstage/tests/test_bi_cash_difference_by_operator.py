"""Quebra de caixa por operador — a métrica que derrubava o explorador.

O commit ``d76a66c70`` ("a custódia é da GAVETA") removeu ``CanonicalShift.operator_key``
e o substituiu por ``operator_keys`` mais ``sole_operator_key``. Ele atualizou os alertas
e a projection de caixa, e **não** atualizou ``bi_explore``. A dataclass é ``frozen`` com
``slots``, então o acesso levantava ``AttributeError`` — que não é erro de domínio, o
``except`` da view não pegava, o handler devolvia ``None`` para exceção não-DRF, e saía um
**500 sem `detail`**. Como o painel só renderiza ``detail``, a tela do gestor ficava **em
branco**, sem mensagem nenhuma. Pior que stacktrace: silêncio.

⚠️ **Por que passou pela suíte.** O único teste que tocava este caminho asseria 200 num
banco **sem nenhum turno fechado** — o laço não executava. Smoke de banco vazio escondendo
bug de linha, que é armadilha já catalogada nesta casa. Por isso todo teste aqui fecha um
turno de verdade.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from django.utils import timezone
from shopman.cashman.models import Entry, Shift, Terminal

METRICA = "cash_difference"


def _auditor() -> User:
    """Quem vê apuração: `view_bi` **e** `cashman.audit_shift` (decisão do dono, 19/08)."""
    user = User.objects.create_user("auditor-bi", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="backstage", codename="view_bi"),
        Permission.objects.get(content_type__app_label="cashman", codename="audit_shift"),
    )
    return User.objects.get(pk=user.pk)


def _turno_fechado(*, terminal_ref: str, quem_abriu: User, lancaram: list[User], diferenca_q: int) -> Shift:
    """Um turno FECHADO, com a diferença provada pelo livro — como o B.I. a lê."""
    terminal, _ = Terminal.objects.get_or_create(ref=terminal_ref, defaults={"label": terminal_ref})
    agora = timezone.now()
    turno = Shift.objects.create(
        terminal=terminal,
        opened_by=quem_abriu,
        opened_at=agora - timedelta(hours=8),
        closed_at=agora - timedelta(hours=1),
        status=Shift.Status.CLOSED,
    )
    # A diferença sai de `count` + correções; quem LANÇOU sai do próprio livro.
    for indice, operador in enumerate(lancaram):
        Entry.objects.create(
            shift=turno,
            operator=operador,
            kind=Entry.Kind.COUNT if indice == 0 else Entry.Kind.COUNT_CORRECTION,
            amount_q=diferenca_q if indice == 0 else 0,
        )
    return turno


@pytest.mark.django_db
def test_a_quebra_por_operador_nao_derruba_mais_o_explorador(client):
    """O chip "Quebra de caixa por operador" com turno fechado no banco.

    Este é o teste que faltava: com o banco vazio o laço nem roda, e o 500 ficava
    invisível.
    """
    auditor = _auditor()
    joyce = User.objects.create_user("joyce", password="pw", is_staff=True)
    _turno_fechado(terminal_ref="balcao", quem_abriu=joyce, lancaram=[joyce], diferenca_q=-1500)
    client.force_login(auditor)

    resposta = client.get(reverse("api-backstage-bi-explore"), {"metric": METRICA, "by": "operator"})

    assert resposta.status_code == 200, "o explorador voltou a cair na quebra por operador"
    linhas = resposta.json()["bi"]["rows"]
    assert {linha["key"] for linha in linhas} == {"joyce"}
    assert linhas[0]["value"] == -1500.0


@pytest.mark.django_db
def test_o_turno_de_uma_pessoa_so_tem_dono(client):
    """`sole_operator_key`: a atribuição é exata quando uma pessoa só lançou."""
    auditor = _auditor()
    joyce = User.objects.create_user("joyce2", password="pw", is_staff=True)
    _turno_fechado(terminal_ref="balcao", quem_abriu=joyce, lancaram=[joyce], diferenca_q=-800)
    client.force_login(auditor)

    linhas = client.get(
        reverse("api-backstage-bi-explore"), {"metric": METRICA, "by": "operator"}
    ).json()["bi"]["rows"]

    assert [(linha["key"], linha["value"]) for linha in linhas] == [("joyce2", -800.0)]


@pytest.mark.django_db
def test_gaveta_compartilhada_nao_inventa_culpado_nem_some_da_soma(client):
    """Com duas pessoas na mesma gaveta não existe conta que divida a quebra.

    Ratear inventaria um culpado — é o que o `sole_operator_key` documenta. Mas
    esconder o turno seria pior de outro jeito: a tela mostraria MENOS quebra do que
    houve. O balde "Gaveta compartilhada" é o que mantém o total honesto.
    """
    auditor = _auditor()
    joyce = User.objects.create_user("joyce3", password="pw", is_staff=True)
    bia = User.objects.create_user("bia3", password="pw", is_staff=True)
    _turno_fechado(terminal_ref="balcao", quem_abriu=joyce, lancaram=[joyce, bia], diferenca_q=-2000)
    client.force_login(auditor)

    linhas = client.get(
        reverse("api-backstage-bi-explore"), {"metric": METRICA, "by": "operator"}
    ).json()["bi"]["rows"]

    assert len(linhas) == 1
    assert linhas[0]["label"] == "Gaveta compartilhada"
    assert linhas[0]["value"] == -2000.0
    assert "joyce3" not in {linha["key"] for linha in linhas}
    assert "bia3" not in {linha["key"] for linha in linhas}


@pytest.mark.django_db
def test_o_total_bate_com_o_livro_mesmo_misturando_os_dois_casos(client):
    """A soma das linhas é a soma do livro — com dono e sem dono no mesmo relatório."""
    auditor = _auditor()
    joyce = User.objects.create_user("joyce4", password="pw", is_staff=True)
    bia = User.objects.create_user("bia4", password="pw", is_staff=True)
    _turno_fechado(terminal_ref="balcao", quem_abriu=joyce, lancaram=[joyce], diferenca_q=-500)
    _turno_fechado(terminal_ref="balcao2", quem_abriu=joyce, lancaram=[joyce, bia], diferenca_q=-1200)
    client.force_login(auditor)

    linhas = client.get(
        reverse("api-backstage-bi-explore"), {"metric": METRICA, "by": "operator"}
    ).json()["bi"]["rows"]

    assert sum(linha["value"] for linha in linhas) == -1700.0
