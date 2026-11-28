"""PDV › Ajustes: o que o operador muda com frequência, lido e editado no app.

UX-15 (Ajustes em todos os apps) e UX-16 (CRUD no Nuxt), prévia
``salao-mesas4.html``: as abas Terminal, Impressoras, Maquininhas, Salão, Envio à
cozinha e Atalhos de venda. Nada aqui cria cadastro novo: cada aba lê e edita o
cadastro que já existe, e a configuração rara continua no Admin.

- **Impressoras**: o rolo e a guilhotina de cada terminal
  (``Terminal.metadata.hardware.printer``), e a impressora de cada estação sem
  tela (``KDSInstance.print_terminal``).
- **Maquininhas**: as maquininhas de entrega (``DeliveryDevice``): nome,
  identificação, ativa, e com quem está agora.
- **Envio à cozinha**: as estações de preparo e separação (``KDSInstance``) com o
  que cada uma recebe e o **envio automático**, opcional por estação e desligado
  por padrão (decisão do dono, SUITE-UX-FUNCTION-PLAN §13, item 3). O interruptor
  mora em ``KDSInstance.config["auto_fire"]``.
- **Atalhos de venda**: as coleções favoritas do terminal
  (``Terminal.metadata.favorite_collection_refs``), que abrem a grade do PDV.

Toda gravação deixa uma linha no log com quem e o quê.

**Quem grava.** Maquininha, impressora e Salão são equipamento e planta da casa:
só o Gerente e o Dono gravam (decisão do dono, 05/11/2026, beta test). A régua é
``cashman.change_terminal``, a mesma do cadastro de terminal no Admin, que a Caixa
não tem. A Caixa lê as três abas, sem gravar. Envio à cozinha e Atalhos de venda
seguem com quem opera o PDV.
"""

from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)

ROLL_WIDTHS = (80, 58)
CUT_MODES = (("partial", "Corte parcial"), ("none", "Sem guilhotina"))


#: Quem grava maquininha, impressora e Salão (Gerente e Dono).
SETUP_PERMISSION = "cashman.change_terminal"
#: As seções do POST que pedem ``SETUP_PERMISSION``.
SETUP_SECTIONS = frozenset({"printer", "card_machine"})
#: O que a recusa diz a quem não pode gravar.
SETUP_REFUSAL = "Maquininha, impressora e Salão são ajustados pelo gerente."
#: Até onde vão o nome e a identificação da maquininha (o banco guarda 100).
CARD_MACHINE_TEXT_MAX = 100


def can_manage_setup(user) -> bool:
    return bool(user and user.is_authenticated and user.has_perm(SETUP_PERMISSION))


class PosSettingsError(Exception):
    def __init__(self, message: str, *, field: str = "", code: str = "invalid"):
        super().__init__(message)
        self.field = field
        self.code = code


def auto_fire_enabled(instance) -> bool:
    """O envio automático da estação: ligado só quando alguém ligou."""
    return bool((instance.config or {}).get("auto_fire"))


def _printer(terminal) -> dict:
    hardware = dict((terminal.metadata or {}).get("hardware") or {})
    printer = dict(hardware.get("printer") or {})
    roll = printer.get("roll_width_mm")
    return {
        "roll_width_mm": int(roll) if str(roll or "").isdigit() else None,
        "cut_mode": str(printer.get("cut_mode") or ""),
    }


def build_settings(*, terminal=None, can_manage_setup: bool = False) -> dict:
    from shopman.cashman.models import Terminal
    from shopman.offerman.models import Collection

    from shopman.backstage.models import DeliveryDevice, KDSInstance

    terminals = list(Terminal.objects.filter(is_active=True).order_by("ref"))
    stations = list(
        KDSInstance.objects.filter(is_active=True)
        .exclude(type="expedition")
        .select_related("print_terminal")
        .prefetch_related("collections")
        .order_by("name")
    )
    printers = [
        {
            "terminal_ref": t.ref,
            "label": t.label or t.ref,
            "location": t.location_ref,
            **_printer(t),
            "stations": [s.name for s in stations if s.print_terminal_id == t.pk],
        }
        for t in terminals
    ]
    devices = [
        {
            "ref": str(d.ref),
            "label": d.label,
            "identification": d.identification,
            "active": d.active,
            "with_order": d.current_order.ref if d.current_order_id else "",
        }
        for d in DeliveryDevice.objects.select_related("current_order").order_by("label", "pk")
    ]
    kitchen = [
        {
            "ref": s.ref,
            "name": s.name,
            "type": s.type,
            "type_label": s.get_type_display(),
            "collections": [c.name for c in s.collections.all()],
            "print_terminal": (s.print_terminal.label or s.print_terminal.ref) if s.print_terminal else "",
            "auto_fire": auto_fire_enabled(s),
        }
        for s in stations
    ]
    current = terminal or (terminals[0] if terminals else None)
    favorites = list((current.metadata or {}).get("favorite_collection_refs") or []) if current else []
    collections = [
        {"ref": c.ref, "name": c.name}
        for c in Collection.objects.filter(is_active=True).order_by("sort_order", "name")
    ]
    return {
        "terminal_ref": current.ref if current else "",
        "terminal_label": (current.label or current.ref) if current else "",
        # O terminal acima é o DESTE dispositivo só quando ele está vinculado a um
        # posto; sem vínculo é o primeiro da loja, e a tela não pode chamá-lo de
        # "este dispositivo" (beta 05/11, CEN-06).
        "terminal_is_this_device": terminal is not None,
        "can_manage_setup": bool(can_manage_setup),
        "printers": printers,
        "roll_widths": list(ROLL_WIDTHS),
        "cut_modes": [{"value": v, "label": label} for v, label in CUT_MODES],
        "card_machines": devices,
        "kitchen_stations": kitchen,
        "shortcuts": {"favorite_collection_refs": favorites, "collections": collections},
    }


@transaction.atomic
def update_printer(*, terminal_ref: str, roll_width_mm, cut_mode: str, actor: str) -> None:
    from shopman.cashman.models import Terminal

    terminal = Terminal.objects.select_for_update().filter(ref=terminal_ref, is_active=True).first()
    if terminal is None:
        raise PosSettingsError("Terminal não encontrado.", field="terminal_ref")
    try:
        roll = int(roll_width_mm)
    except (TypeError, ValueError):
        roll = 0
    if roll not in ROLL_WIDTHS:
        raise PosSettingsError("Escolha o rolo de 80 mm ou de 58 mm.", field="roll_width_mm")
    if cut_mode not in {v for v, _ in CUT_MODES}:
        raise PosSettingsError("Escolha se a impressora corta o papel.", field="cut_mode")
    metadata = dict(terminal.metadata or {})
    hardware = dict(metadata.get("hardware") or {})
    printer = dict(hardware.get("printer") or {})
    printer.update({"roll_width_mm": roll, "cut_mode": cut_mode})
    hardware["printer"] = printer
    metadata["hardware"] = hardware
    terminal.metadata = metadata
    terminal.save(update_fields=["metadata", "updated_at"])
    logger.info("pos_settings_printer terminal=%s roll=%s cut=%s actor=%s", terminal.ref, roll, cut_mode, actor)


@transaction.atomic
def save_card_machine(
    *, ref: str, label: str, identification: str, active: bool, actor: str, identification_sent: bool = True,
) -> None:
    from shopman.backstage.models import DeliveryDevice

    label = (label or "").strip()
    identification = (identification or "").strip()
    if not label:
        raise PosSettingsError("Dê um nome à maquininha.", field="label")
    # O banco guarda 100; passar disso era um 500 com "Não deu para gravar"
    # (beta 05/11, PDV-11).
    if len(label) > CARD_MACHINE_TEXT_MAX:
        raise PosSettingsError(f"Use no máximo {CARD_MACHINE_TEXT_MAX} caracteres no nome.", field="label")
    if len(identification) > CARD_MACHINE_TEXT_MAX:
        raise PosSettingsError(
            f"Use no máximo {CARD_MACHINE_TEXT_MAX} caracteres na identificação.", field="identification",
        )
    if ref:
        device = DeliveryDevice.objects.select_for_update().filter(ref=ref).first()
        if device is None:
            raise PosSettingsError("Maquininha não encontrada.", field="ref")
        if not active and device.current_order_id:
            raise PosSettingsError("Esta maquininha está numa entrega agora. Desative quando ela voltar.", field="active")
        # Ligar e desligar manda só o nome; a edição manda a identificação, e
        # apagá-la ali é engano, não "manter a antiga" calado (beta 05/11, PDV-27).
        if identification_sent and not identification:
            raise PosSettingsError(
                "Escreva a identificação (o número de série ou a etiqueta da maquininha).", field="identification",
            )
    else:
        if not identification:
            raise PosSettingsError("Escreva a identificação (o número de série ou a etiqueta da maquininha).", field="identification")
        device = DeliveryDevice()
    if identification:
        # "SN-001" e "sn-001" são a mesma etiqueta colada na maquininha.
        clash = DeliveryDevice.objects.filter(identification__iexact=identification).exclude(pk=device.pk).exists()
        if clash:
            raise PosSettingsError("Já existe uma maquininha com essa identificação.", field="identification")
        device.identification = identification
    device.label = label
    device.active = bool(active)
    device.save()
    logger.info("pos_settings_card_machine ref=%s active=%s actor=%s", device.ref, device.active, actor)


@transaction.atomic
def set_station_auto_fire(*, station_ref: str, enabled: bool, actor: str) -> None:
    from shopman.backstage.models import KDSInstance

    station = KDSInstance.objects.select_for_update().filter(ref=station_ref, is_active=True).exclude(type="expedition").first()
    if station is None:
        raise PosSettingsError("Estação não encontrada.", field="station_ref")
    config = dict(station.config or {})
    config["auto_fire"] = bool(enabled)
    station.config = config
    station.save(update_fields=["config"])
    logger.info("pos_settings_auto_fire station=%s enabled=%s actor=%s", station.ref, bool(enabled), actor)


@transaction.atomic
def set_favorite_collections(*, terminal_ref: str, refs: list, actor: str) -> None:
    from shopman.cashman.models import Terminal
    from shopman.offerman.models import Collection

    terminal = Terminal.objects.select_for_update().filter(ref=terminal_ref, is_active=True).first()
    if terminal is None:
        raise PosSettingsError("Terminal não encontrado.", field="terminal_ref")
    if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
        raise PosSettingsError("Envie a lista de coleções.", field="favorite_collection_refs")
    known = set(Collection.objects.filter(ref__in=refs).values_list("ref", flat=True))
    clean = [r for r in dict.fromkeys(refs) if r in known]
    metadata = dict(terminal.metadata or {})
    metadata["favorite_collection_refs"] = clean
    metadata.pop("favorite_collections", None)
    terminal.metadata = metadata
    terminal.save(update_fields=["metadata", "updated_at"])
    logger.info("pos_settings_shortcuts terminal=%s refs=%s actor=%s", terminal.ref, clean, actor)
