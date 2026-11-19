"""O sábado abreviado leva acento ("Sáb"), em toda tela que abrevia o dia.

A tradução do Django traz "Sab". O projeto sobrescreve em ``locale/pt_BR`` (auditoria
da prévia do WP-G10 do Gestor, 19/11/2026: "Sab, 21/11" no cabeçalho do dia).
"""

from __future__ import annotations

from datetime import date, timedelta

from django.utils import formats, timezone, translation

from shopman.backstage.projections.order_attention import commitment_day_label

SATURDAY = date(2026, 11, 21)
WEEK = (date(2026, 11, 16), ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"))


def test_o_sabado_abreviado_leva_acento():
    with translation.override("pt-br"):
        assert formats.date_format(SATURDAY, "D") == "Sáb"


def test_a_semana_inteira_abreviada():
    monday, names = WEEK
    with translation.override("pt-br"):
        assert tuple(formats.date_format(monday + timedelta(days=i), "D") for i in range(7)) == names


def test_o_rotulo_do_dia_combinado_diz_sab():
    """A régua do selo do cartão, da lista de Encomendas e da agenda do Gestor."""
    today = timezone.localdate()
    # O próximo sábado que não seja hoje, amanhã nem ontem (esses têm nome próprio).
    day = today + timedelta(days=2)
    while day.weekday() != 5:
        day += timedelta(days=1)
    with translation.override("pt-br"):
        assert commitment_day_label(day) == f"Sáb, {day:%d/%m}"
