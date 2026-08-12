"""Runtime profile and diagnostics for POS terminals."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TerminalComponentHealth:
    key: str
    label: str
    status: str
    message: str


@dataclass(frozen=True)
class PrinterGeometry:
    """Geometria de impressão declarada pelo terminal.

    Tudo em zero significa "o terminal não declarou" — e aí quem manda é o
    default do CSS do PDV (rolo de 80mm). O default tem UM dono, o CSS; este
    serviço só fala quando a loja declarou outra coisa.
    """

    roll_width_mm: int = 0
    margin_mm: int = 0
    problem: str = ""

    @property
    def declared(self) -> bool:
        return self.roll_width_mm > 0 and self.margin_mm > 0


@dataclass(frozen=True)
class TerminalRuntimeProfile:
    terminal_ref: str
    terminal_label: str
    default_fulfillment_type: str
    favorite_collection_refs: tuple[str, ...]
    components: tuple[TerminalComponentHealth, ...]
    printer: PrinterGeometry = PrinterGeometry()

    @property
    def status(self) -> str:
        if any(component.status == "error" for component in self.components):
            return "error"
        if any(component.status == "warning" for component in self.components):
            return "warning"
        return "ready"


_COMPONENT_LABELS = {
    "printer": "Impressora",
    "cash_drawer": "Gaveta",
    "scanner": "Leitor",
    "payment_terminal": "TEF/adquirente",
    "customer_display": "Display cliente",
}


def runtime_profile(terminal) -> TerminalRuntimeProfile:
    metadata = dict(getattr(terminal, "metadata", None) or {})
    hardware = dict(metadata.get("hardware") or {})
    printer = printer_geometry(dict(hardware.get("printer") or {}))
    components = tuple(
        _component_health(
            key,
            dict(hardware.get(key) or {}),
            problem=printer.problem if key == "printer" else "",
        )
        for key in _COMPONENT_LABELS
    )
    return TerminalRuntimeProfile(
        terminal_ref=terminal.ref,
        terminal_label=terminal.label or terminal.ref,
        default_fulfillment_type=_default_fulfillment_type(metadata),
        favorite_collection_refs=_favorite_collection_refs(metadata),
        components=components,
        printer=printer,
    )


# Largura de rolo → largura que o cabeçote realmente alcança. NÃO é proporcional:
# a 203dpi, a térmica de 80mm imprime 576 dots (72,07mm) e a de 58mm imprime 384
# (48,13mm). Por isso a margem de um rolo de 58mm é 5mm, não os 4mm do de 80mm —
# quem regra de três aqui corta a coluna do preço.
_ROLL_PRINT_WIDTH_MM = {80: 72, 58: 48}
_ROLL_WIDTH_BOUNDS = (40, 120)


def printer_geometry(config: dict) -> PrinterGeometry:
    """Lê a geometria que o terminal declarou em ``metadata.hardware.printer``.

    A loja declara o que ela sabe: ``roll_width_mm``, a largura do rolo que
    compra. A área imprimível sai da tabela dos dois padrões de mercado; um
    modelo fora do padrão precisa declarar ``print_width_mm`` explicitamente,
    porque chutar aqui é imprimir para fora do papel.

    Declaração inválida NÃO cai calada para o default: volta como ``problem``,
    que vira ``warning`` na saúde do terminal. Config ignorada em silêncio é o
    mesmo buraco de uma `var()` que não resolve — a tela mente que está tudo bem.
    """
    raw_roll = config.get("roll_width_mm")
    if raw_roll in (None, ""):
        return PrinterGeometry()

    roll = _positive_int(raw_roll)
    low, high = _ROLL_WIDTH_BOUNDS
    if roll is None or not low <= roll <= high:
        return PrinterGeometry(problem=f"largura de rolo inválida ({raw_roll!r})")

    raw_print = config.get("print_width_mm")
    if raw_print in (None, ""):
        printable = _ROLL_PRINT_WIDTH_MM.get(roll)
        if printable is None:
            return PrinterGeometry(
                problem=f"rolo de {roll}mm fora do padrão — declare print_width_mm",
            )
    else:
        printable = _positive_int(raw_print)
        if printable is None or printable >= roll:
            return PrinterGeometry(problem=f"largura de impressão inválida ({raw_print!r})")

    # Arredonda a margem para cima: sobrar 0,5mm de papel é barato, invadir a
    # faixa que o cabeçote não alcança custa o fim da linha impressa.
    return PrinterGeometry(roll_width_mm=roll, margin_mm=(roll - printable + 1) // 2)


def _positive_int(value) -> int | None:
    """Inteiro positivo a partir de JSON frouxo (``80``, ``"80"``, ``80.0``)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not number.is_integer() or number <= 0:
        return None
    return int(number)


def _component_health(key: str, config: dict, *, problem: str = "") -> TerminalComponentHealth:
    """Saúde de um periférico do terminal.

    Ausência não é defeito. Um balcão sem display do cliente ou sem leitor está
    COMPLETO do jeito que a loja montou — antes ele contava como ``warning``, e
    como nenhum terminal declara ``metadata.hardware``, o badge nascia em
    "Atenção" e ficava aceso para sempre. Alerta que nunca apaga é alerta que
    ninguém lê: quando a impressora caísse de verdade, teria a mesma cara.

    Agora só é ``warning`` o periférico que a loja DECLAROU e que não está
    pronto para uso. Declarado com adapter — inclusive um adapter real, que
    antes era tratado como suspeito e o simulado como saudável, exatamente ao
    contrário — vale ``ready``.
    """
    label = _COMPONENT_LABELS[key]
    if not config:
        return TerminalComponentHealth(key=key, label=label, status="absent", message="não instalado")
    if config.get("enabled") is False:
        return TerminalComponentHealth(key=key, label=label, status="absent", message="desligado")
    if problem:
        # Declarado e mal declarado: pior que não declarar, porque a loja acha
        # que configurou. Aparece na saúde do terminal com o motivo.
        return TerminalComponentHealth(key=key, label=label, status="warning", message=problem)
    adapter = str(config.get("adapter") or "").strip()
    if adapter:
        return TerminalComponentHealth(key=key, label=label, status="ready", message=adapter)
    return TerminalComponentHealth(key=key, label=label, status="warning", message="sem adapter")


def _default_fulfillment_type(metadata: dict) -> str:
    value = str(metadata.get("default_fulfillment_type") or "pickup").strip().lower()
    return "delivery" if value == "delivery" else "pickup"


def _favorite_collection_refs(metadata: dict) -> tuple[str, ...]:
    raw = metadata.get("favorite_collection_refs") or metadata.get("favorite_collections") or []
    if not isinstance(raw, list):
        return ()
    refs = []
    for ref in raw:
        value = str(ref or "").strip()
        if value and value not in refs:
            refs.append(value)
    return tuple(refs[:9])
