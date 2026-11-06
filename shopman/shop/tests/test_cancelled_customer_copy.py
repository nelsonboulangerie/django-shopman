"""O cancelamento solicitado pelo cliente forma uma frase só em todos os canais."""

from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps

from shopman.shop.adapters._notification_templates import derive_context, render_message, strip_markdown_bold
from shopman.shop.notification_copy import CUSTOMER_COPY
from shopman.shop.services.cancel_reasons import customer_text
from shopman.shop.services.notification import _status_note


def test_customer_requested_cancellation_matches_approved_copy():
    data = {"cancellation_reason": "customer_requested"}
    order = SimpleNamespace(data=data)
    context = {
        "order_ref": "NB-261106-V55",
        "customer_name": "Pablo Valentini",
        "status_note": _status_note(order, "order_cancelled", None),
        "tracking_url": "https://www.nelsonboulangerie.com.br/pedido/NB-261106-V55",
    }
    body = render_message("order_cancelled", context, {"order_cancelled": CUSTOMER_COPY["order_cancelled"]["body"]})
    assert strip_markdown_bold(body) == (
        "Oi, Pablo Valentini. Seu pedido V55 foi cancelado, conforme sua solicitação. "
        "Qualquer dúvida, estamos à disposição. 😌\n"
        "Veja os detalhes: https://www.nelsonboulangerie.com.br/pedido/NB-261106-V55"
    )
    # O modelo aprovado na Meta continua recebendo uma variável não vazia.
    assert context["status_note"] == "Conforme sua solicitação."


def test_customer_request_rebuilds_note_from_saved_reason():
    order = SimpleNamespace(data={"cancellation_reason_key": "customer_request"})
    assert _status_note(order, "order_cancelled", None, note="Motivo anterior.") == "Conforme sua solicitação."


def test_other_reasons_keep_complete_sentence_and_punctuation():
    note = customer_text({"cancellation_reason_key": "out_of_stock"})
    ctx = derive_context({"status_note": note})
    assert ctx["cancellation_reason_suffix"] == f". {note}"
    assert derive_context(ctx) == ctx
    assert derive_context({})["cancellation_reason_suffix"] == "."


@pytest.mark.django_db
def test_migration_updates_only_previous_default():
    from shopman.shop.models import NotificationTemplate

    migration = import_module("shopman.shop.migrations.0111_cancelamento_conforme_solicitacao")
    template = NotificationTemplate.objects.create(event="order_cancelled", body=migration.OLD_BODY)
    migration.forwards(apps, None)
    template.refresh_from_db()
    assert template.body == CUSTOMER_COPY["order_cancelled"]["body"]
    version = template.version
    migration.forwards(apps, None)
    template.refresh_from_db()
    assert template.version == version
    template.body = "Nosso texto personalizado."
    template.save()
    migration.forwards(apps, None)
    template.refresh_from_db()
    assert template.body == "Nosso texto personalizado."
