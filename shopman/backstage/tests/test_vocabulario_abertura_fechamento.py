"""Trava do vocabulário do ciclo do lote (parecer do dono, 03/10/2026).

O kernel do Craftsman modela ``planned → started → finished`` (e ``void``). A
camada pt-BR fala Planejada · Aberta · Fechada · Cancelada; os eventos
``started``/``finished`` são Abertura e Fechamento. "Produzido" chegou a
significar ``started`` no quadro da Produção e ``finished`` no Admin; esta trava
impede que volte a rotular qualquer um dos dois.

O rótulo do status tem UMA fonte: os choices de ``WorkOrder.Status``. A projeção
da Produção, o Admin e o OpenAPI leem dali; nenhuma camada redefine.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from shopman.craftsman.models import WorkOrder, WorkOrderEvent

from shopman.backstage.projections.production import WO_STATUS_LABELS

ROOT = Path(__file__).resolve().parents[3]

CANONICAL_STATUS = {
    "planned": "Planejada",
    "started": "Aberta",
    "finished": "Fechada",
    "void": "Cancelada",
}

#: Onde o ciclo do lote é rotulado para gente ler (Admin, quadro, relatórios,
#: alertas). Nenhum destes arquivos pode ter um texto que COMECE por Produzido
#: (rótulo de coluna, de status ou de evento). "SKU produzido" da ficha técnica
#: é outra coisa e continua livre.
LIFECYCLE_SOURCES = (
    "packages/craftsman/shopman/craftsman/models/work_order.py",
    "packages/craftsman/shopman/craftsman/models/work_order_event.py",
    "packages/craftsman/shopman/craftsman/contrib/admin_unfold/admin.py",
    "packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py",
    "shopman/backstage/projections/production.py",
    "shopman/backstage/services/production.py",
    "shopman/backstage/projections/hub_queue.py",
    "shopman/shop/handlers/production_alerts.py",
)

PRODUCED = re.compile(r"[\"']Produzid[oa]s?\b")


def test_status_da_workorder_fala_o_vocabulario_canonico():
    assert {status.value: str(status.label) for status in WorkOrder.Status} == CANONICAL_STATUS


def test_eventos_de_abertura_e_fechamento():
    assert str(WorkOrderEvent.Kind.STARTED.label) == "Abertura"
    assert str(WorkOrderEvent.Kind.FINISHED.label) == "Fechamento"


def test_projecao_le_os_rotulos_da_fonte_unica():
    assert WO_STATUS_LABELS == CANONICAL_STATUS


def test_openapi_le_os_rotulos_da_fonte_unica():
    from drf_spectacular.plumbing import deep_import_string

    override = settings.SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]["CraftsmanWorkOrderStatusEnum"]
    # Caminho, não lista: uma lista copiada aqui seria uma segunda fonte.
    assert isinstance(override, str)
    assert deep_import_string(override) is WorkOrder.Status


def test_produzido_nao_rotula_started_nem_finished():
    hits = [
        f"{relative}:{number}"
        for relative in LIFECYCLE_SOURCES
        for number, line in enumerate((ROOT / relative).read_text(encoding="utf-8").splitlines(), start=1)
        if PRODUCED.search(line)
    ]
    assert hits == []
