"""Voz dos avisos do ciclo do pedido (decisão do dono, 24/09/2026).

Três coisas que o texto sozinho não garante:

1. ``{eta_note}`` diz a MESMA hora que a tela de acompanhamento (uma âncora de
   relógio só: ``projections.order_tracking._eta_at``) e some fora do preparo;
2. a migração ``0075`` leva os textos novos ao banco já semeado sem tocar no que
   o lojista reescreveu no Admin;
3. a migração e o ``seed`` não divergem — o texto que chega pelo deploy é o mesmo
   que nasceria de um reseed.
"""

from __future__ import annotations

import ast
from datetime import datetime
from importlib import import_module
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.apps import apps
from django.conf import settings
from django.utils import timezone

from shopman.shop.adapters import notification_email, notification_manychat
from shopman.shop.services.notification import _eta_note

MIGRATION = import_module("shopman.shop.migrations.0075_voz_dos_avisos_do_pedido")


def _order(status: str):
    order = MagicMock()
    order.ref = "ORD-1"
    order.status = status
    return order


def test_eta_note_usa_a_hora_da_tela():
    eta = timezone.make_aware(datetime(2026, 9, 24, 18, 20))
    with patch("shopman.shop.projections.order_tracking._eta_at", return_value=eta.isoformat()) as tela:
        note = _eta_note(_order("preparing"))

    tela.assert_called_once()
    assert note == f"\nDeve ficar pronto às {timezone.localtime(eta).hour}h20."


def test_eta_note_em_hora_cheia_nao_diz_zero_zero():
    eta = timezone.localtime(timezone.make_aware(datetime(2026, 9, 24, 18, 0)))
    with patch("shopman.shop.projections.order_tracking._eta_at", return_value=eta.isoformat()):
        assert _eta_note(_order("preparing")) == f"\nDeve ficar pronto às {eta.hour}h."


def test_eta_note_some_sem_hora_e_fora_do_preparo():
    with patch("shopman.shop.projections.order_tracking._eta_at", return_value=None):
        assert _eta_note(_order("preparing")) == ""
    # No despacho o `_eta_at` é a hora de CHEGADA: "pronto às" mentiria.
    with patch(
        "shopman.shop.projections.order_tracking._eta_at",
        return_value=timezone.now().isoformat(),
    ):
        assert _eta_note(_order("dispatched")) == ""


def _seeded_templates() -> dict:
    seed = Path(settings.BASE_DIR) / "config" / "management" / "commands" / "seed.py"
    tree = ast.parse(seed.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "FALLBACK_TEMPLATES" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("FALLBACK_TEMPLATES sumiu do seed")


def test_migracao_chega_ao_mesmo_texto_do_seed():
    seeded = _seeded_templates()
    for event, _old_subject, new_subject, _old_body, new_body in MIGRATION.TEXTS:
        assert seeded[event]["subject"] == new_subject, event
        assert seeded[event]["body"] == new_body, event


@pytest.mark.django_db
def test_migracao_troca_so_o_texto_antigo_do_seed():
    from shopman.shop.models import NotificationTemplate

    event, old_subject, new_subject, old_body, new_body = next(
        row for row in MIGRATION.TEXTS if row[0] == "order_ready_delivery"
    )
    NotificationTemplate.objects.create(event=event, subject=old_subject, body=old_body)
    reescrito = NotificationTemplate.objects.create(
        event="order_preparing", subject="Assunto da casa", body="Texto que o lojista escreveu."
    )

    MIGRATION.forwards(apps, None)

    tpl = NotificationTemplate.objects.get(event=event)
    assert (tpl.subject, tpl.body) == (new_subject, new_body)
    reescrito.refresh_from_db()
    assert (reescrito.subject, reescrito.body) == ("Assunto da casa", "Texto que o lojista escreveu.")

    MIGRATION.backwards(apps, None)
    tpl.refresh_from_db()
    assert (tpl.subject, tpl.body) == (old_subject, old_body)


DISPATCHED = import_module("shopman.shop.migrations.0076_saiu_para_entrega_sem_cumprimento")


def test_saida_para_entrega_nao_cumprimenta_e_bate_com_o_seed():
    body = _seeded_templates()["order_dispatched"]["body"]
    assert body == DISPATCHED.NEW_BODY
    assert "customer_name_greeting" not in body
    for fallback in (
        notification_email.BODY_TEMPLATES["order_dispatched"],
        notification_manychat.MESSAGE_TEMPLATES["order_dispatched"],
    ):
        assert fallback.startswith("Seu pedido {order_ref} saiu para entrega e chega logo.")


@pytest.mark.django_db
def test_migracao_da_saida_troca_so_o_texto_antigo_do_seed():
    from shopman.shop.models import NotificationTemplate

    tpl = NotificationTemplate.objects.create(
        event="order_dispatched", subject="Pedido {order_ref} saiu para entrega", body=DISPATCHED.OLD_BODY
    )
    DISPATCHED.forwards(apps, None)
    tpl.refresh_from_db()
    assert tpl.body == DISPATCHED.NEW_BODY

    tpl.body = "Texto que o lojista escreveu."
    tpl.save(update_fields=["body"])
    DISPATCHED.backwards(apps, None)
    DISPATCHED.forwards(apps, None)
    tpl.refresh_from_db()
    assert tpl.body == "Texto que o lojista escreveu."
