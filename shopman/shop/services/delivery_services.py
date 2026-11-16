"""Qual serviço leva a corrida, e o que ele sabe fazer (DEV-2026-030, frente M1).

Plano: ``docs/plans/DELIVERY-MULTI-SERVICE-PLAN.md`` §2. Este é o único lugar que responde
"qual módulo fala com o serviço desta corrida". Todo código de entrega pede o módulo aqui,
nunca a ``get_adapter("courier")`` direto.

O contrato de um módulo de serviço de entrega (hoje ``adapters/courier_machine``, a TaOn; na
M2, o entregador da casa) é o que a TaOn já expõe, mais duas peças:

- ``CAPABILITIES``: um ``DeliveryCapabilities`` (``shopman.shop.protocols``);
- ``ride_state(status)``: o estado próprio do serviço traduzido para ``RideState``.

Comportamento na M1, de propósito igual ao de antes: a corrida da TaOn resolve o mesmo
módulo de sempre (``get_adapter("courier")``: ``Shop.integrations`` e depois ``settings``),
e nenhuma leitura de banco entra no caminho quente. O serviço padrão só é lido quando uma
corrida nova é aberta, para gravar ``courier.service``.
"""

from __future__ import annotations

from shopman.shop.adapters import get_adapter
from shopman.shop.models.delivery_service import DeliveryService
from shopman.shop.protocols import DeliveryCapabilities, RideState

#: ``ref`` → ``kind``. O tipo de um serviço não muda depois de criado (o Admin trava
#: ``ref`` e ``kind``), então a resposta pode morar no processo.
_KIND_BY_REF: dict[str, str] = {}


def _kind(ref: str) -> str | None:
    if ref not in _KIND_BY_REF:
        kind = DeliveryService.objects.filter(ref=ref).values_list("kind", flat=True).first()
        if kind is None:
            return None
        _KIND_BY_REF[ref] = kind
    return _KIND_BY_REF[ref]


def courier_backend(block: dict | None = None):
    """O módulo que fala com o serviço da corrida, ou None quando não há serviço ligado.

    Sem bloco (ou corrida aberta antes da M1, sem ``service``) vale a central de entregas
    configurada, como sempre. Serviço sem módulo próprio ainda (o entregador da casa, até
    a M2) responde None: não há central para chamar.
    """
    ref = str((block or {}).get("service") or "")
    if ref:
        kind = _kind(ref)
        if kind is not None and kind not in DeliveryService.KINDS_WITH_BACKEND:
            return None
    return get_adapter("courier")


def service_for_new_ride() -> DeliveryService | None:
    """O serviço que leva a corrida que está sendo aberta agora: o padrão do Admin."""
    return DeliveryService.default()


def new_ride_service_ref() -> str:
    """O ``ref`` do serviço padrão, gravado em ``courier.service`` quando a corrida abre ("" sem serviço)."""
    service = service_for_new_ride()
    return service.ref if service else ""


def capabilities(block: dict | None = None) -> DeliveryCapabilities | None:
    """O que o serviço da corrida sabe fazer, ou None sem serviço ligado."""
    return getattr(courier_backend(block), "CAPABILITIES", None)


def ride_state(block: dict | None) -> RideState | None:
    """O estado da corrida no vocabulário da casa, a partir do estado cru do serviço."""
    if not block:
        return None
    translate = getattr(courier_backend(block), "ride_state", None)
    return translate(block.get("status")) if translate else None
