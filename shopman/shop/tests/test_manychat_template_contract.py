"""O contrato de campos de cada flow cobre TODA variável do template aprovado.

O adapter grava no perfil do ManyChat só os campos declarados em
``flow_fields_for_event`` (``notification_manychat._push_custom_fields``). Uma
variável que o template usa e o contrato não declara não é reescrita: o flow lê o
valor da mensagem ANTERIOR. Medido em 02/10/2026: o ``pedido_cancelado`` aprovado
usa ``status_note`` no corpo e ``order_ref`` no botão, e o ``order_cancelled`` não
declarava nenhum dos dois. O cliente recebia o motivo e o link de outro pedido.

A fonte das variáveis é o documento de referência dos templates, o mesmo que se
usa para submeter à Meta: corpo (``- Vars:``) e botão (``(`campo`)`` na linha do
botão). Template novo no documento entra nesta trava sem ninguém lembrar dela.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from shopman.shop.services import manychat_marketing_safety as safety

_DOC = Path(__file__).resolve().parents[3] / "docs" / "reference" / "whatsapp-templates-meta.md"
_SECTION = re.compile(r"^### `(\w+)` — evento `(\w+)`(.*?)(?=^### |^## |\Z)", re.S | re.M)
_FIELD = re.compile(r"\(`(\w+)`[,)]")

#: Eventos do documento que NÃO são transacionais: Marketing tem contrato próprio,
#: conferido em ``test_manychat_flow_isolation``.
_MARKETING = {"production_ready", "announcement_published"}


def _template_fields() -> dict[str, set[str]]:
    fields: dict[str, set[str]] = {}
    for match in _SECTION.finditer(_DOC.read_text(encoding="utf-8")):
        _name, event, body = match.groups()
        if event in _MARKETING:
            continue
        used: set[str] = set()
        for line in body.splitlines():
            if line.startswith("- Vars:") or "Botão" in line or "botões" in line:
                used.update(_FIELD.findall(line))
        fields[event] = used
    return fields


def test_the_reference_document_was_read():
    fields = _template_fields()
    assert len(fields) >= 25, sorted(fields)
    assert fields["order_cancelled"] >= {"customer_name", "order_ref_short", "status_note", "order_ref"}


@pytest.mark.parametrize("event", sorted(_template_fields()))
def test_every_template_variable_is_written_on_every_send(event):
    declared = set(safety.flow_fields_for_event(event) or ())
    missing = _template_fields()[event] - declared
    assert not missing, (
        f"{event}: o template usa {sorted(missing)} e o contrato não declara. "
        "O flow leria o valor da mensagem anterior."
    )
