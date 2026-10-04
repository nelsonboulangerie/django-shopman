"""O que o serviço do KDS diz à Cozinha usa o vocabulário da Cozinha.

O ato de terminar o ticket se chama **Pronto** (decisão do dono, 04/10/2026), e o
botão que confirma um item cancelado se chama **Recebi o cancelamento**. Ver
``docs/reference/suite-vocabulary.md`` §1 e §4. As mensagens de ``services/kds.py``
chegam ao tablet como aviso; um verbo de outro app ou um botão que não existe
manda o cozinheiro procurar o que não está na tela.

A Produção fica de fora: lá *finalizar* é o último passo do Fechamento do lote.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from shopman.orderman.models import Order

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.shop.models import Channel
from shopman.shop.services import kds as kds_core

REPO_ROOT = Path(__file__).resolve().parents[3]
KDS_SERVICE = Path(kds_core.__file__)
KDS_BOARD_PAGE = REPO_ROOT / "surfaces" / "kds-nuxt" / "app" / "pages" / "[ref].vue"

# Montadas em pedaços para este arquivo não se reprovar se alguém o varrer.
BANNED = re.compile("|".join(["final" + "iz", r"\bCi" + r"ente\b"]), re.IGNORECASE)
ACK_BUTTON = "Recebi o cancelamento"


def _string_literals(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_service_strings_do_not_use_another_apps_verb():
    offenders = [f"kds.py:{n}: {s.strip()[:90]}" for n, s in _string_literals(KDS_SERVICE) if BANNED.search(s)]
    assert offenders == [], 'use "Pronto" e o rótulo real do botão ("Recebi o cancelamento")'


def test_the_ban_is_not_blind():
    assert BANNED.search("toque em Ci" + "ente antes de final" + "izar")
    assert BANNED.search("a final" + "ização não pode mais ser desfeita")
    assert not BANNED.search("o Pronto não pode mais ser desfeito")


def test_ack_button_label_is_the_one_the_board_shows():
    """A mensagem cita o botão pelo nome; o nome tem de existir na tela."""
    if not KDS_BOARD_PAGE.exists():
        pytest.skip("kds-nuxt fora deste checkout")
    assert ACK_BUTTON in KDS_BOARD_PAGE.read_text(encoding="utf-8")


@pytest.mark.django_db
def test_unacknowledged_cancel_blocks_ready_naming_the_button():
    Channel.objects.create(ref="pdv", name="PDV")
    Order.objects.create(
        ref="ORD-KDS-VOC",
        channel_ref="pdv",
        session_key="sk-kds-voc",
        status=Order.Status.PREPARING,
        total_q=1000,
    )
    station = KDSInstance.objects.create(ref="lanches", name="Lanches", type="prep")
    live = KDSTicket.objects.create(
        session_key="sk-kds-voc",
        kds_instance=station,
        status="in_progress",
        items=[{"sku": "A", "name": "Item", "qty": 1}],
    )
    KDSTicket.objects.create(
        session_key="sk-kds-voc",
        kds_instance=station,
        status="cancelled",
        items=[{"sku": "B", "name": "Outro", "qty": 1}],
    )

    with pytest.raises(kds_core.TicketCompletionBlocked) as exc:
        kds_core.complete_ticket(live, actor="kds:op")

    message = str(exc.value)
    assert ACK_BUTTON in message
    assert "Pronto" in message
    assert not BANNED.search(message)
