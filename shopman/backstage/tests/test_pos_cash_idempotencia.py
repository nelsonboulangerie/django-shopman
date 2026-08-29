"""A rede do salão oscila, e o operador toca de novo.

⚠️ As oito mutações de dinheiro do caixa declaravam ``idempotency="none"`` e não tinham
trava nenhuma. O operador lança uma sangria de R$ 200, a rede oscila (é a mesma do kiosk
e do KDS), o botão não responde, ele toca de novo — e o livro-caixa aceita as duas
linhas. O livro é **imutável de propósito**, então o conserto não é apagar: é um ajuste,
com o gerente, no fechamento, com o dono perguntando por que faltam R$ 200.

E não havia segunda linha de defesa: as ``UniqueConstraint`` que o cashman acrescentou
depois de um TOCTOU real cobrem só os ``kind`` que têm ``order_ref``. Sangria,
suprimento, fundo de troco, devolução e acerto de conta são exatamente os que **não**
têm. A trava de banco que salvou a venda não alcançava o caixa.

**Nenhum modelo novo e nenhuma migração:** a trava reusa a ``IdempotencyKey`` do orderman
pelo envelope genérico ``run_idempotent_mutation`` — a mesma máquina do commit de sessão,
do replay de webhook e do submit da venda.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.cashman.models import Entry, Shift, Terminal

CHAVE = "pos-cash:teste-1"


@pytest.fixture
def operador(db):
    user = User.objects.create_user("caixa-idem", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"
        )
    )
    return User.objects.get(pk=user.pk)


@pytest.fixture
def gerente(db):
    from shopman.doorman.models import PinCredential

    user = User.objects.create_user("gerente-idem", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Shift), codename="adjust_shift"
        )
    )
    PinCredential.set_for(user, "4321")
    return user


@pytest.fixture
def turno_aberto(db, operador):
    Terminal.objects.get_or_create(ref="balcao", defaults={"label": "Balcão"})
    from shopman.backstage.services import pos as pos_service

    return pos_service.open_cash_shift(
        operator=operador, opening_amount_raw="100,00", terminal_ref="balcao"
    )


def _movimento(client, *, chave, valor="200,00", gerente=None):
    corpo = {"kind": "sangria", "amount": valor, "reason": "retirada do meio-dia"}
    if chave:
        corpo["client_request_id"] = chave
    if gerente:
        corpo["manager_approval"] = {"username": gerente.username, "pin": "4321"}
    return client.post(
        reverse("api-backstage-pos-cash-movement"), data=corpo, content_type="application/json"
    )


@pytest.mark.django_db
def test_a_mesma_sangria_com_a_mesma_chave_lanca_UMA_vez(client, operador, gerente, turno_aberto):
    """O toque duplo depois do timeout: o servidor já gravou, a resposta se perdeu."""
    client.force_login(operador)

    primeira = _movimento(client, chave=CHAVE, gerente=gerente)
    assert primeira.status_code == 200, primeira.content

    segunda = _movimento(client, chave=CHAVE, gerente=gerente)

    # Replay é SILENCIOSO: a chave é ESTE GESTO, e a tela a descarta no sucesso —
    # então um segundo envio com a mesma chave só pode ser retry da mesma sangria.
    assert segunda.status_code == 200
    lancamentos = Entry.objects.filter(shift=turno_aberto, kind=Entry.Kind.CASH_OUT)
    assert lancamentos.count() == 1, "o livro-caixa ficou com duas linhas de R$ 200"


@pytest.mark.django_db
def test_chaves_diferentes_lancam_duas_vezes(client, operador, gerente, turno_aberto):
    """Assert-positivo: a trava não pode virar uma porta fechada.

    Duas sangrias deliberadamente iguais são dois lançamentos — e é por isso que a
    tela descarta a chave no sucesso, em vez de derivá-la do conteúdo.
    """
    client.force_login(operador)

    assert _movimento(client, chave="pos-cash:a", gerente=gerente).status_code == 200
    assert _movimento(client, chave="pos-cash:b", gerente=gerente).status_code == 200

    assert Entry.objects.filter(shift=turno_aberto, kind=Entry.Kind.CASH_OUT).count() == 2


@pytest.mark.django_db
def test_sem_chave_cada_envio_e_uma_operacao(client, operador, gerente, turno_aberto):
    """Mesma régua do submit da venda: sem chave não há o que travar.

    A tela sempre manda uma; quem chama a API crua sem chave está dizendo que cada
    envio é uma operação. O teste fixa isso para ninguém achar que a trava é mágica.
    """
    client.force_login(operador)

    assert _movimento(client, chave=None, gerente=gerente).status_code == 200
    assert _movimento(client, chave=None, gerente=gerente).status_code == 200

    assert Entry.objects.filter(shift=turno_aberto, kind=Entry.Kind.CASH_OUT).count() == 2


@pytest.mark.django_db
def test_uma_recusa_NAO_e_guardada_para_replay(client, operador, gerente, turno_aberto):
    """Guardar um 400 faria o operador que corrigiu o valor receber o erro antigo.

    A trava existe para não duplicar dinheiro, não para congelar um engano.
    """
    client.force_login(operador)

    recusada = _movimento(client, chave=CHAVE, valor="0,00", gerente=gerente)
    assert recusada.status_code >= 400

    corrigida = _movimento(client, chave=CHAVE, valor="200,00", gerente=gerente)

    assert corrigida.status_code == 200, corrigida.content
    assert Entry.objects.filter(shift=turno_aberto, kind=Entry.Kind.CASH_OUT).count() == 1
