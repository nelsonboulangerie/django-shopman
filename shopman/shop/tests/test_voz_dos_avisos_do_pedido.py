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
DISPATCHED = import_module("shopman.shop.migrations.0076_saiu_para_entrega_sem_cumprimento")


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


SHORT_REF = import_module("shopman.shop.migrations.0077_mensagem_chama_pedido_pelo_final")


def _through_later_migrations(event: str, subject: str, body: str) -> tuple[str, str]:
    """O texto que uma migração deixou, depois das migrações de texto seguintes."""
    if event == "order_dispatched" and body == DISPATCHED.OLD_BODY:
        body = DISPATCHED.NEW_BODY
    for row_event, old_subject, new_subject, old_body, new_body in SHORT_REF.TEXTS:
        if row_event == event:
            subject = new_subject if subject == old_subject else subject
            body = new_body if body == old_body else body
    return subject, body


def test_migracao_chega_ao_mesmo_texto_do_seed():
    seeded = _seeded_templates()
    for event, _old_subject, new_subject, _old_body, new_body in MIGRATION.TEXTS:
        subject, body = _through_later_migrations(event, new_subject, new_body)
        assert seeded[event]["subject"] == subject, event
        assert seeded[event]["body"] == body, event


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


def test_saida_para_entrega_nao_cumprimenta_e_bate_com_o_seed():
    seeded = _seeded_templates()["order_dispatched"]
    assert (seeded["subject"], seeded["body"]) == _through_later_migrations(
        "order_dispatched", seeded["subject"], DISPATCHED.NEW_BODY
    )
    assert "customer_name_greeting" not in seeded["body"]
    for fallback in (
        notification_email.BODY_TEMPLATES["order_dispatched"],
        notification_manychat.MESSAGE_TEMPLATES["order_dispatched"],
    ):
        assert fallback.startswith("Seu pedido {order_ref_short} saiu para entrega.")


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


# ── O pedido é chamado pelo final do ref (decisão do dono, 25/09/2026) ─────────


def test_contexto_traz_o_final_do_ref_e_mantem_o_ref_completo():
    from shopman.shop.adapters._notification_templates import derive_context

    ctx = derive_context({"order_ref": "NB-260925-A47"})
    assert ctx["order_ref_short"] == "A47"
    assert ctx["order_ref"] == "NB-260925-A47"
    assert derive_context({})["order_ref_short"] == ""


def test_migracao_do_final_bate_com_o_seed():
    seeded = _seeded_templates()
    for event, _old_subject, new_subject, _old_body, new_body in SHORT_REF.TEXTS:
        assert (seeded[event]["subject"], seeded[event]["body"]) == (new_subject, new_body), event


def test_nenhuma_mensagem_ao_cliente_diz_o_ref_completo():
    """No texto, o pedido é o final; o ref completo só vive no link."""
    from shopman.shop.adapters import notification_sms

    textos = {f"seed:{k}": v["subject"] + v["body"] for k, v in _seeded_templates().items()}
    textos |= {f"email:{k}": v for k, v in notification_email.SUBJECT_TEMPLATES.items()}
    textos |= {f"email:{k}": v for k, v in notification_email.BODY_TEMPLATES.items()}
    textos |= {f"manychat:{k}": v for k, v in notification_manychat.MESSAGE_TEMPLATES.items()}
    textos |= {f"sms:{k}": v for k, v in notification_sms.MESSAGE_TEMPLATES.items()}
    # O alerta crítico vai ao OPERADOR, que busca pelo ref completo.
    culpados = [k for k, v in textos.items() if "{order_ref}" in v and not k.endswith(":operator_critical")]
    assert culpados == []
