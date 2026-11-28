"""Trava do vocabulário do ciclo do lote (parecer do dono, 03/10/2026).

O kernel do Craftsman modela ``planned → started → finished`` (e ``void``). A
camada pt-BR fala Planejada · Em produção · Finalizada · Cancelada (dono,
28/11/2026: "Aberto/Fechado é nomenclatura vencida... o que era fechamento virou
Finalização"; o lote que passou pelo Confirmar está em produção); os eventos
``started``/``finished`` são Produção e Finalização. "Produzido" chegou a
significar ``started`` no quadro da Produção e ``finished`` no Admin; esta trava
impede que volte a rotular qualquer um dos dois.

O rótulo do status tem UMA fonte: os choices de ``WorkOrder.Status``. A projeção
da Produção, o Admin e o OpenAPI leem dali; nenhuma camada redefine.

O indicador do lote é o APROVEITAMENTO = realizado ÷ previsto (UX-PROD-AF2,
decisão do dono, 03/10/2026). "Rendimento" fica reservado à ficha técnica e à
massa: o B.I. e o uso por versão do livro de receitas não o usam para o lote.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from django.conf import settings
from shopman.craftsman.models import WorkOrder, WorkOrderEvent

from shopman.backstage.projections.production import WO_STATUS_LABELS

ROOT = Path(__file__).resolve().parents[3]

CANONICAL_STATUS = {
    "planned": "Planejada",
    "started": "Em produção",
    "finished": "Finalizada",
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
    assert str(WorkOrderEvent.Kind.STARTED.label) == "Produção"
    assert str(WorkOrderEvent.Kind.FINISHED.label) == "Finalização"


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


#: Onde o indicador do LOTE é calculado para o B.I. Nada aqui fala da ficha
#: técnica nem da massa, então "rendimento" não tem uso legítimo.
LOT_INDICATOR_SOURCES = (
    "shopman/backstage/projections/bi_production.py",
    "shopman/backstage/projections/bi_explore.py",
    "shopman/backstage/bi/scenarios.py",
)


def test_bi_chama_o_indicador_do_lote_de_aproveitamento():
    from shopman.backstage.projections.bi_explore import METRICS

    assert METRICS["yield_percent"].label == "Aproveitamento"
    hits = [
        f"{relative}:{number}"
        for relative in LOT_INDICATOR_SOURCES
        for number, line in enumerate((ROOT / relative).read_text(encoding="utf-8").splitlines(), start=1)
        if re.search(r"rendimento", line, re.IGNORECASE)
    ]
    assert hits == []


def test_uso_por_versao_fala_aproveitamento():
    source = (ROOT / "shopman/backstage/projections/recipe_book.py").read_text(encoding="utf-8")
    assert "rendimento médio" not in source
    assert "aproveitamento médio" in source


# ── Aberto/Fechado não volta ao texto que o servidor entrega à Produção (#3691) ──
#
# Os identificadores (``started``/``finished``, ``open``/``close``, ``closed_by``)
# ficam; o TEXTO do lote é "em produção" e "finalizado". A trava lê só os literais
# de string (sem comentário e sem docstring) dos arquivos que falam do lote ao
# operador: o caixa ("turno aberto às 7h") e a loja ("Aberta", "Fechada") têm outro
# vocabulário e moram fora desta lista.
LOT_TEXT_SOURCES = (
    *LIFECYCLE_SOURCES,
    "shopman/backstage/models/alerts.py",
    "shopman/backstage/projections/alerts.py",
    "shopman/shop/models/quality.py",
    # O B.I. lê o lote finalizado (#3696): o mesmo texto na tela do gestor.
    "shopman/backstage/projections/bi_over_short.py",
    "shopman/backstage/projections/bi_production.py",
)

LOT_OPEN_CLOSED = re.compile(
    r"\b(?:lotes?|fornadas?|enfornadas?)\s+(?:ainda\s+)?(?:n[aã]o\s+|j[aá]\s+|nunca\s+)?(?:abert|fechad)[oa]s?\b"
    r"|\b(?:fechar|abrir|feche|abra)\s+(?:(?:o|os|a|as)\s+)?(?:lotes?|fornadas?)\b"
    r"|\bnunca\s+foi\s+(?:abert|fechad)[oa]\b"
    r"|\b(?:abert|fechad)[oa]s?\s+(?:em|por|às|há)\b"
    r"|\bem\s+aberto\b",
    re.IGNORECASE,
)


def _string_literals(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


def test_o_detector_conhece_as_formas_vencidas():
    for text in (
        "Somente a gestão pode revisar um lote fechado.",
        "Lote aberto nunca fechado",
        "Não dá para fechar o lote WO-1",
        "Feche o lote com o que ele rendeu.",
        "WO-1 · aberto às 6h",
        "Fechado por",
        "Aberta em",
        "nunca foi aberto.",
        "Este lote já possui uma enfornada aberta.",
    ):
        assert LOT_OPEN_CLOSED.search(text), text
    for text in ("Caixa aberto", "antes de fechar", "Fechar o painel", "Loja fechada", "Lote em produção"):
        assert not LOT_OPEN_CLOSED.search(text), text


def test_o_texto_do_lote_diz_em_producao_e_finalizado():
    hits = [
        f"{relative}:{line}: {text!r}"
        for relative in LOT_TEXT_SOURCES
        for line, text in _string_literals(ROOT / relative)
        if LOT_OPEN_CLOSED.search(text)
    ]
    assert hits == []


def test_o_letreiro_diz_finalizado():
    from shopman.backstage.projections.production import _FORECAST_STATUS_LABELS

    assert _FORECAST_STATUS_LABELS["arrived"] == "Finalizado"
