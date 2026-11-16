"""A coluna de data nativa do Admin escreve a hora como a casa: "12h45".

O que o código formata passa por ``format_clock``; aqui é o que o Django formata
sozinho (``DateTimeField`` no changelist, ``|date`` sem argumento), pelo módulo de
formato ``config/formats/pt_BR/formats.py``.
"""

from __future__ import annotations

from datetime import datetime, time

from django.conf import settings
from django.utils import formats, translation


def test_o_modulo_de_formato_da_casa_esta_ligado():
    assert "config.formats" in settings.FORMAT_MODULE_PATH


def test_data_e_hora_do_django_saem_no_formato_da_casa():
    moment = datetime(2026, 11, 16, 12, 45)
    with translation.override("pt-br"):
        assert formats.date_format(moment, "DATETIME_FORMAT") == "16 de Novembro de 2026 às 12h45"
        assert formats.date_format(moment, "SHORT_DATETIME_FORMAT") == "16/11/2026 12h45"
        assert formats.time_format(time(9, 5), "TIME_FORMAT") == "9h05"


def test_campo_de_formulario_continua_aceitando_a_forma_do_campo():
    with translation.override("pt-br"):
        assert "%H:%M" in formats.get_format("TIME_INPUT_FORMATS")
