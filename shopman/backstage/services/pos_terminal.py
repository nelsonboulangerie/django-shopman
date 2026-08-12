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
class TerminalRuntimeProfile:
    terminal_ref: str
    terminal_label: str
    default_fulfillment_type: str
    favorite_collection_refs: tuple[str, ...]
    components: tuple[TerminalComponentHealth, ...]

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
    components = tuple(
        _component_health(key, dict(hardware.get(key) or {}))
        for key in _COMPONENT_LABELS
    )
    return TerminalRuntimeProfile(
        terminal_ref=terminal.ref,
        terminal_label=terminal.label or terminal.ref,
        default_fulfillment_type=_default_fulfillment_type(metadata),
        favorite_collection_refs=_favorite_collection_refs(metadata),
        components=components,
    )


def _component_health(key: str, config: dict) -> TerminalComponentHealth:
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
