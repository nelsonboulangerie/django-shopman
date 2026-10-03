"""As palavras dos POSTOS de trabalho, numa fonte só.

O dono ainda está decidindo nomes ("Expedição" ou "Saída", o nome da sala de fechar
lote da Produção). Por isso nenhum rótulo de tipo de posto e nenhuma frase da tela de
provisionar mora em outro lugar: o backend lê daqui, a projection entrega à tela, e o
kit (``surfaces/operator-kit/app/presentation/workstation.ts``) tem só o espelho
tipado das CHAVES, nunca do texto. Renomear é mudar uma linha aqui.

Os tipos não são ``choices`` do campo de propósito: ``choices`` congelam o rótulo na
migração, e renomear um tipo viraria migração. A validação é contra as chaves deste
mapa (``Workstation.clean``).

Prosa em português, identificador em inglês (CLAUDE.md). Sem travessão e sem a palavra
que não usamos para o objeto do operador: o objeto é sempre *dispositivo*.
"""

from __future__ import annotations

#: Caixa: o único posto com gaveta e turno, amarrado a um ``cashman.Terminal``.
CASH_DESK = "cash_desk"
#: Atendimento: comanda na mesa, sem gaveta.
SERVICE = "service"
#: Expedição: o tablet onde se confere e entrega ou despacha o pedido pronto.
DISPATCH = "dispatch"
#: Estação da Cozinha: Lanches, Cafés.
KITCHEN_STATION = "kitchen_station"
#: Sala da Produção: Massas, Molde, Laminação, Preparos, Forno.
PRODUCTION_ROOM = "production_room"
#: Escritório: ajustar, comprar, ler.
OFFICE = "office"

#: Tipo de posto → rótulo. A ordem é a ordem das listas na tela.
KIND_LABELS: dict[str, str] = {
    CASH_DESK: "Caixa",
    SERVICE: "Atendimento",
    DISPATCH: "Expedição",
    KITCHEN_STATION: "Estação da Cozinha",
    PRODUCTION_ROOM: "Sala da Produção",
    OFFICE: "Escritório",
}

#: Que postos cada app OFERECE ao provisionar. O posto é um só para todos os apps (o
#: cookie vale no domínio inteiro); isto só decide o que faz sentido listar em cada
#: um. As chaves são os ids de ``surfaces/registry.json``.
SURFACE_KINDS: dict[str, tuple[str, ...]] = {
    "hub": tuple(KIND_LABELS),
    "pos": (CASH_DESK, SERVICE),
    "kds": (KITCHEN_STATION, DISPATCH),
    "orders": (DISPATCH, OFFICE),
    "production": (PRODUCTION_ROOM,),
    "marketing": (OFFICE,),
    "purchase": (OFFICE,),
    "bi": (OFFICE,),
}

#: A copy da tela de provisionar, do contexto no rail e do cadastro. Proposta do dono
#: em validação (03/10/2026).
COPY: dict[str, str] = {
    "setup_title": "Este dispositivo fica em qual posto?",
    "setup_lead": (
        "Escolha uma vez. Depois ele abre direto no trabalho deste posto e pede só o "
        "PIN de quem for operar."
    ),
    "setup_choice_label": "Postos deste app",
    "setup_confirm": "Fixar neste posto",
    "setup_confirm_shared": "Fixar também neste posto",
    "setup_busy": "Fixando…",
    "setup_dismiss": "Agora não",
    "setup_error": "Não foi possível fixar este dispositivo no posto.",
    "setup_empty": (
        "Ainda não há posto para este app. Quem gere operadores cadastra os postos "
        "no Gestor, em Postos."
    ),
    "context_prefix": "Posto",
    "release": "Soltar deste posto",
    "cash_desk_hint": "Com gaveta e turno",
    "devices_one": "1 dispositivo",
    "devices_many": "{n} dispositivos",
    "open_shift_hint": "caixa aberto",
    "shared_cash_desk": (
        "Este caixa já tem {others}. Todos vão usar a mesma gaveta e o mesmo turno. "
        "Confirme para fixar este dispositivo no mesmo posto."
    ),
    "unknown": "Posto não encontrado.",
    "not_a_workstation": "Este dispositivo não está fixado em nenhum posto.",
    "manage_title": "Postos",
    "manage_lead": (
        "Onde cada dispositivo fica. Fixado num posto, ele abre direto no trabalho "
        "do posto e pede só o PIN de quem for operar."
    ),
    "manage_new": "Novo posto",
    "manage_name_label": "Nome do posto",
    "manage_kind_label": "Tipo",
    "manage_create": "Criar posto",
    "manage_rename": "Renomear",
    "manage_save": "Salvar",
    "manage_deactivate": "Desativar posto",
    "manage_deactivate_warning": "Desativar solta todos os dispositivos deste posto.",
    "manage_keep_active": "Manter ativo",
    "manage_activate": "Reativar posto",
    "manage_inactive": "Desativado",
    "manage_cash_desk_note": "O posto Caixa nasce com o caixa, no cadastro de terminais.",
    "manage_devices_none": "Nenhum dispositivo fixado neste posto.",
    "manage_device_last_used": "Usado por último em {when}",
    "manage_device_never_used": "Ainda não usado",
    "manage_error": "Não foi possível salvar o posto.",
}


def kind_label(kind: str) -> str:
    """O rótulo do tipo, ou o próprio valor quando o tipo saiu do mapa."""
    return KIND_LABELS.get(kind, kind)


def kinds_for_surface(surface: str) -> tuple[str, ...]:
    """Os tipos que o app oferece. App desconhecido oferece todos (é a Central)."""
    return SURFACE_KINDS.get(str(surface or "").strip(), tuple(KIND_LABELS))


def devices_label(count: int) -> str:
    return COPY["devices_one"] if count == 1 else COPY["devices_many"].format(n=count)
