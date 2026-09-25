"""Voz dos avisos ao cliente (decisões do dono, 24 e 25/09/2026).

O que o texto sozinho não garante:

1. ``{status_note}`` nunca fica vazia: é a hora prevista (a MESMA que a tela mostra:
   ``projections.order_tracking._eta_at``) ou o motivo, e sem o dado entra a
   frase-padrão. É o que a deixa caber no template da Meta.
2. Os fallbacks de cada canal saem da fonte única (``shopman/shop/notification_copy``):
   nenhum canal diverge do texto que o dono revisou.
3. As migrações de texto (0075 → 0078) levam o banco já semeado ao mesmo texto de
   um reseed, sem tocar no que o lojista reescreveu no Admin.
4. O WhatsApp não manda "Oi, !": pedido sem nome passa a vez para o SMS/e-mail.
"""

from __future__ import annotations

from datetime import datetime
from importlib import import_module
from unittest.mock import MagicMock, patch

import pytest
from django.apps import apps
from django.utils import timezone

from config.management.commands.seed import NOTIFICATION_TEMPLATES
from shopman.shop import notification_copy
from shopman.shop.adapters import notification_email, notification_manychat, notification_sms
from shopman.shop.services.notification import _status_note

TEXT_MIGRATIONS = [
    import_module("shopman.shop.migrations.0075_voz_dos_avisos_do_pedido"),
    import_module("shopman.shop.migrations.0077_mensagem_chama_pedido_pelo_final"),
    import_module("shopman.shop.migrations.0078_frases_revisadas_das_notificacoes"),
    import_module("shopman.shop.migrations.0079_confirmado_com_todo_carinho"),
]
DISPATCHED = import_module("shopman.shop.migrations.0076_saiu_para_entrega_sem_cumprimento")
REVISED = TEXT_MIGRATIONS[-2]


def _order(status: str):
    order = MagicMock()
    order.ref = "ORD-1"
    order.status = status
    return order


# ── 1. status_note ─────────────────────────────────────────────────────────────


def test_status_note_do_preparo_usa_a_hora_da_tela():
    eta = timezone.make_aware(datetime(2026, 9, 24, 18, 20))
    with patch("shopman.shop.projections.order_tracking._eta_at", return_value=eta.isoformat()) as tela:
        note = _status_note(_order("preparing"), "order_preparing", None)

    tela.assert_called_once()
    hour = timezone.localtime(eta).hour
    # Sem ponto final: o ponto é do texto (o template da Meta não termina em variável).
    assert note == f"Previsto para ficar pronto às {hour}h20. Mas avisamos assim que estiver"


def test_status_note_em_hora_cheia_nao_diz_zero_zero():
    eta = timezone.localtime(timezone.make_aware(datetime(2026, 9, 24, 18, 0)))
    with patch("shopman.shop.projections.order_tracking._eta_at", return_value=eta.isoformat()):
        note = _status_note(_order("preparing"), "order_preparing", None)
    assert f"às {eta.hour}h." in note


def test_status_note_do_preparo_sem_hora_tem_frase_padrao():
    with patch("shopman.shop.projections.order_tracking._eta_at", return_value=None):
        assert _status_note(_order("preparing"), "order_preparing", None) == "Avisamos assim que estiver pronto"


def test_status_note_do_cancelamento_diz_o_motivo_ou_aponta_o_pedido():
    order = _order("cancelled")
    assert _status_note(order, "order_cancelled", "item indisponível") == "Motivo: item indisponível."
    assert _status_note(order, "order_rejected", None) == "Os detalhes estão no pedido."


def test_status_note_so_existe_onde_o_texto_a_usa():
    users = {e for e, c in notification_copy.CUSTOMER_COPY.items() if "{status_note}" in c["body"]}
    assert users == {"order_preparing", "order_cancelled", "order_rejected"}


# ── 2. Fonte única ────────────────────────────────────────────────────────────


def test_seed_grava_a_fonte_unica():
    for event, copy in notification_copy.CUSTOMER_COPY.items():
        assert NOTIFICATION_TEMPLATES[event] == copy, event


def test_fallbacks_saem_da_fonte_unica():
    for event, copy in notification_copy.CUSTOMER_COPY.items():
        assert notification_manychat.MESSAGE_TEMPLATES[event] == copy["body"], event
        assert notification_email.BODY_TEMPLATES[event] == copy["body"].replace("*", ""), event
        assert notification_email.SUBJECT_TEMPLATES[event] == copy["subject"], event
        assert notification_sms.MESSAGE_TEMPLATES[event].isascii(), event


def test_a_voz_e_da_concierge():
    """No feminino, emoji só os da casa, e ninguém começa com o nome solto."""
    for event, copy in notification_copy.CUSTOMER_COPY.items():
        body = copy["body"]
        assert "Obrigado" not in body, event
        assert not body.startswith("{customer_name"), event
        for emoji in ("\U0001f950", "\U0001f956", "\U0001f4e6", "\U0001f389", "⭐"):
            assert emoji not in body, (event, emoji)


def test_nenhuma_mensagem_ao_cliente_diz_o_ref_completo():
    """No texto, o pedido é o final; o ref completo só vive no link."""
    textos = {f"seed:{k}": v["subject"] + v["body"] for k, v in NOTIFICATION_TEMPLATES.items()}
    textos |= {f"email:{k}": v for k, v in notification_email.SUBJECT_TEMPLATES.items()}
    textos |= {f"email:{k}": v for k, v in notification_email.BODY_TEMPLATES.items()}
    textos |= {f"manychat:{k}": v for k, v in notification_manychat.MESSAGE_TEMPLATES.items()}
    textos |= {f"sms:{k}": v for k, v in notification_sms.MESSAGE_TEMPLATES.items()}
    # O alerta crítico vai ao OPERADOR, que busca pelo ref completo.
    culpados = [k for k, v in textos.items() if "{order_ref}" in v and not k.endswith(":operator_critical")]
    assert culpados == []


def test_contexto_traz_o_final_do_ref_e_mantem_o_ref_completo():
    from shopman.shop.adapters._notification_templates import derive_context

    ctx = derive_context({"order_ref": "NB-260925-A47"})
    assert ctx["order_ref_short"] == "A47"
    assert ctx["order_ref"] == "NB-260925-A47"
    assert derive_context({})["order_ref_short"] == ""


# ── 3. Migrações de texto ─────────────────────────────────────────────────────


def _through_later_migrations(event: str, subject: str, body: str, *, after) -> tuple[str, str]:
    """O texto que uma migração deixou, depois das migrações de texto seguintes."""
    # A 0076 (saída para entrega) fica entre a 0075 e a 0077.
    later = TEXT_MIGRATIONS[TEXT_MIGRATIONS.index(after) + 1 :] if after in TEXT_MIGRATIONS else TEXT_MIGRATIONS[1:]
    if event == "order_dispatched" and body == DISPATCHED.OLD_BODY:
        body = DISPATCHED.NEW_BODY
    for migration in later:
        for row_event, old_subject, new_subject, old_body, new_body in migration.TEXTS:
            if row_event == event:
                subject = new_subject if subject == old_subject else subject
                body = new_body if body == old_body else body
    return subject, body


@pytest.mark.parametrize("migration", TEXT_MIGRATIONS, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_cada_migracao_de_texto_chega_ao_texto_do_seed(migration):
    for event, _old_subject, new_subject, _old_body, new_body in migration.TEXTS:
        final = _through_later_migrations(event, new_subject, new_body, after=migration)
        seeded = NOTIFICATION_TEMPLATES[event]
        assert (seeded["subject"], seeded["body"]) == final, event


def test_a_saida_para_entrega_chega_ao_texto_do_seed():
    seeded = NOTIFICATION_TEMPLATES["order_dispatched"]
    subject, body = _through_later_migrations(
        "order_dispatched", seeded["subject"], DISPATCHED.NEW_BODY, after=DISPATCHED
    )
    assert body == seeded["body"]


@pytest.mark.django_db
def test_a_migracao_troca_so_o_texto_antigo_do_seed():
    from shopman.shop.models import NotificationTemplate

    event, old_subject, new_subject, old_body, new_body = next(
        row for row in REVISED.TEXTS if row[0] == "order_preparing"
    )
    NotificationTemplate.objects.create(event=event, subject=old_subject, body=old_body)
    reescrito = NotificationTemplate.objects.create(
        event="order_accepted", subject="Assunto da casa", body="Texto que o lojista escreveu."
    )

    REVISED.forwards(apps, None)

    tpl = NotificationTemplate.objects.get(event=event)
    assert (tpl.subject, tpl.body) == (new_subject, new_body)
    reescrito.refresh_from_db()
    assert (reescrito.subject, reescrito.body) == ("Assunto da casa", "Texto que o lojista escreveu.")

    REVISED.backwards(apps, None)
    tpl.refresh_from_db()
    assert (tpl.subject, tpl.body) == (old_subject, old_body)


# ── 4. WhatsApp sem nome ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("template", "name", "lacks"),
    [
        ("order_received", "", True),  # "Oi, {{1}}!" sem nome
        ("order_received", "Ana", False),
        ("order_accepted", "", False),  # não cumprimenta
        ("stock_arrived", "", False),  # não é aviso de pedido (vive no alerta de estoque)
    ],
)
def test_flow_sem_nome_passa_a_vez(template, name, lacks):
    assert notification_manychat._flow_lacks_name(template, {"customer_name": name}) is lacks


def test_availability_note_nunca_vazia_e_sem_ponto():
    from shopman.shop.services.availability_copy import availability_note

    assert availability_note(12) == "No momento temos 12 un. disponíveis"
    assert availability_note(1) == "No momento temos 1 un. disponível"
    assert availability_note(None) == "Já está disponível para pedido"
