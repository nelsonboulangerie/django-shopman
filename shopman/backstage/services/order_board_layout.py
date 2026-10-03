"""A arrumação das colunas do Gestor, lembrada por POSTO.

Entrada, Preparo e Saída podem ser recolhidas numa faixa e ter a largura ajustada
(SUITE-UX §16). O tablet do passe fica só com a Saída; o PC do gestor, com as três.
Essa arrumação é da casa, não do navegador (lei L7): trocar o tablet, limpar o
navegador ou recarregar não pode desfazer o jeito do posto.

**Onde mora.** O posto já tem registro com JSON de configuração: o ``Terminal`` da
estação confiável (``station_trust.station_ref``), cujo ``metadata`` o backstage já
escreve (``hardware``, ``station``). A arrumação entra ali, na chave
``gestor_board`` (inventário em ``docs/reference/data-schemas.md``). Nenhum modelo
novo, nenhuma migração, nada no Core além do JSON que ele oferece para isso.

**Sem posto, sem memória no servidor.** Um navegador que não é estação confiável (o
notebook do gestor, por exemplo) não tem de quem ser a arrumação; ele abre com as
três colunas e o que mudar vale até recarregar. Não há fallback por pessoa: o
quadro de uma pessoa muda de posto para posto, e é o posto que decide.
"""

from __future__ import annotations

from django.db import transaction

#: As zonas do quadro, na ordem da tela (``presentation/board.ts``: ``ZoneView.key``).
ZONES: tuple[str, ...] = ("intake", "prep", "expedition")

#: Chave em ``Terminal.metadata``.
METADATA_KEY = "gestor_board"

WEIGHT_MIN = 0.25
WEIGHT_MAX = 4.0


class LayoutError(ValueError):
    """Arrumação recusada; a mensagem vai ao operador."""


def normalize_columns(raw) -> dict[str, dict]:
    """Valida o que a tela mandou. Recusa em vez de adivinhar.

    Toda zona precisa vir, com ``open`` booleano e ``weight`` dentro da faixa; zona
    desconhecida é recusada (não guardamos lixo no posto); e pelo menos uma coluna
    fica aberta, porque a fila não pode sumir da tela.
    """
    if not isinstance(raw, dict):
        raise LayoutError("Arrumação inválida: esperava as colunas do quadro.")
    unknown = sorted(set(raw) - set(ZONES))
    if unknown:
        raise LayoutError(f"Coluna desconhecida: {', '.join(unknown)}.")
    columns: dict[str, dict] = {}
    for zone in ZONES:
        entry = raw.get(zone)
        if not isinstance(entry, dict):
            raise LayoutError(f"Falta a coluna {zone}.")
        open_ = entry.get("open")
        weight = entry.get("weight")
        if not isinstance(open_, bool):
            raise LayoutError(f"A coluna {zone} precisa dizer se está aberta.")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise LayoutError(f"A largura da coluna {zone} precisa ser um número.")
        if not WEIGHT_MIN <= float(weight) <= WEIGHT_MAX:
            raise LayoutError(f"A largura da coluna {zone} está fora da faixa.")
        columns[zone] = {"open": open_, "weight": round(float(weight), 2)}
    if not any(column["open"] for column in columns.values()):
        raise LayoutError("Pelo menos uma coluna fica aberta.")
    return columns


def _terminal(terminal_ref: str, *, for_update: bool = False):
    from shopman.cashman.models import Terminal

    queryset = Terminal.objects.filter(ref=terminal_ref, is_active=True)
    if for_update:
        queryset = queryset.select_for_update()
    return queryset.first()


def read_columns(terminal_ref: str) -> dict[str, dict] | None:
    """A arrumação guardada no posto, ou ``None`` (nunca mexeram, ou guardado inválido)."""
    if not terminal_ref:
        return None
    terminal = _terminal(terminal_ref)
    if terminal is None:
        return None
    metadata = terminal.metadata if isinstance(terminal.metadata, dict) else {}
    block = metadata.get(METADATA_KEY)
    if not isinstance(block, dict):
        return None
    try:
        return normalize_columns(block.get("columns"))
    except LayoutError:
        return None


def save_columns(terminal_ref: str, raw) -> dict[str, dict] | None:
    """Grava a arrumação no posto, sem tocar nas outras chaves do ``metadata``.

    Devolve ``None`` quando o posto não existe (ou saiu do ar). Trava a linha para
    não apagar, por corrida, o que o Admin do terminal estiver salvando ao lado.
    """
    columns = normalize_columns(raw)
    with transaction.atomic():
        terminal = _terminal(terminal_ref, for_update=True)
        if terminal is None:
            return None
        metadata = dict(terminal.metadata) if isinstance(terminal.metadata, dict) else {}
        metadata[METADATA_KEY] = {"columns": columns}
        terminal.metadata = metadata
        terminal.save(update_fields=["metadata"])
    return columns
