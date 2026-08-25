"""O selo "Na cozinha" do balcão passa a seguir o ticket.

Achado do QA do dono: a linha disparada ganhava um selo fixo — "Na cozinha" — e
ele ficava lá até a venda fechar. O ticket virava "Pronto", ou era cancelado pela
cozinha, e quem estava no caixa só descobria clicando em "Atualizar". Ou não
descobria: entregava um pedido que a cozinha havia cancelado, ou segurava o
cliente esperando algo que já estava no balcão.

Aqui se prova a fonte (o estado por SKU sai dos tickets da comanda) e o push (o
mesmo fato do KDS é contado ao balcão num canal com a permissão DELE, carregando
só a chave da comanda).
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.projections.pos import _kitchen_status_by_sku
from shopman.shop.eventstream import ShopmanChannelManager

pytestmark = pytest.mark.django_db


@pytest.fixture
def estacao():
    return KDSInstance.objects.create(ref="bancada", name="Bancada", type="prep")


def _ticket(estacao, *, skus, status, session_key="sess-1"):
    return KDSTicket.objects.create(
        session_key=session_key,
        kds_instance=estacao,
        items=[{"sku": sku, "name": sku, "qty": 1} for sku in skus],
        status=status,
    )


# ── O estado por SKU ──────────────────────────────────────────────────────


def test_o_estado_de_cada_sku_vem_do_ticket_da_comanda(estacao):
    _ticket(estacao, skus=["PAO"], status="done")
    _ticket(estacao, skus=["BOLO"], status="in_progress")

    assert _kitchen_status_by_sku("sess-1") == {"PAO": "done", "BOLO": "in_progress"}


def test_sku_em_duas_estacoes_so_esta_pronto_quando_as_DUAS_terminam(estacao):
    """Vence o MENOS avançado: meia cozinha pronta não é a linha pronta."""
    outra = KDSInstance.objects.create(ref="forno", name="Forno", type="prep")
    _ticket(estacao, skus=["PAO"], status="done")
    _ticket(outra, skus=["PAO"], status="in_progress")

    assert _kitchen_status_by_sku("sess-1") == {"PAO": "in_progress"}


def test_cancelado_vence_tudo(estacao):
    """É o único estado que pede ação de quem está no caixa."""
    outra = KDSInstance.objects.create(ref="forno", name="Forno", type="prep")
    _ticket(estacao, skus=["PAO"], status="done")
    _ticket(outra, skus=["PAO"], status="cancelled")

    assert _kitchen_status_by_sku("sess-1") == {"PAO": "cancelled"}


def test_comanda_sem_ticket_nao_inventa_estado(estacao):
    assert _kitchen_status_by_sku("sess-vazia") == {}
    assert _kitchen_status_by_sku("") == {}


# ── O push, e a permissão dele ────────────────────────────────────────────


def test_o_balcao_le_o_canal_das_comandas_sem_ganhar_a_cozinha_junto():
    """Assinar o canal `kds` resolveria o push e abriria demais.

    Ali trafega o board inteiro da cozinha, e quem opera o caixa não tem
    `operate_kds`. O canal `tabs` existe para o balcão ouvir que a cozinha mexeu
    numa comanda DELE, com a permissão dele e carregando só a chave.
    """
    manager = ShopmanChannelManager()
    caixa = get_user_model().objects.create_user("marina", password="x", is_staff=True)
    caixa.user_permissions.add(Permission.objects.get(codename="operate_pos"))
    caixa = get_user_model().objects.get(pk=caixa.pk)  # limpa o cache de permissões

    assert manager.can_read_channel(caixa, "backstage-tabs-main") is True
    assert manager.can_read_channel(caixa, "backstage-kds-main") is False


def test_a_cozinha_nao_le_o_canal_do_balcao():
    manager = ShopmanChannelManager()
    cozinha = get_user_model().objects.create_user("cozinha", password="x", is_staff=True)
    cozinha.user_permissions.add(Permission.objects.get(codename="operate_kds"))
    cozinha = get_user_model().objects.get(pk=cozinha.pk)

    assert manager.can_read_channel(cozinha, "backstage-tabs-main") is False


def test_mudar_o_ticket_anuncia_a_comanda_ao_balcao(estacao, django_capture_on_commit_callbacks, monkeypatch):
    """O MESMO fato, contado duas vezes: para a cozinha e para o balcão.

    O corpo do aviso do balcão é sinal mínimo (ADR-016) — a chave da comanda e
    mais nada. Quem recebe refaz o fetch canônico da Projection do terminal, que
    já é filtrada pelo gate do PDV.
    """
    enviados: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(
        "shopman.shop.handlers._sse_emitters._publish_backstage",
        lambda kind, event_type, payload, scope: enviados.append((kind, event_type, payload)),
    )

    with django_capture_on_commit_callbacks(execute=True):
        ticket = _ticket(estacao, skus=["PAO"], status="pending")
    enviados.clear()

    with django_capture_on_commit_callbacks(execute=True):
        ticket.status = "done"
        ticket.save(update_fields=["status"])

    kinds = {kind for kind, _, _ in enviados}
    assert "kds" in kinds
    assert "tabs" in kinds
    avisos = [p for kind, _, p in enviados if kind == "tabs"]
    assert avisos  # o balcão foi avisado
    # Sinal mínimo: a chave da comanda e mais nada. Nenhum dado da cozinha
    # atravessa para uma tela que não tem permissão de vê-lo.
    assert all(a == {"kind": "kitchen", "session_key": "sess-1"} for a in avisos)
