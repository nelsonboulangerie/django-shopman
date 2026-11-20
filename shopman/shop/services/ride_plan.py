"""O plano das corridas: quem vai junto com quem (P1-9, o desenho do juiz, frente F5).

Um plano só, no servidor, lido por todas as telas que juntam entregas: o cartão de
sugestões no topo de Aguardando (página Entregas), a oferta "Vai junto nesta corrida?"
do Painel do pedido (``ride_offer``) e a contagem "Montar corridas (N sugeridas)" do
Painel. Como as três leem a MESMA partição, nunca discordam.

A regra (relatório da revisão, seção 4; parâmetros decididos pelo dono em 16/11/2026):

1. **Quem entra:** pedido Pronto, com coordenada, que pode ir com outros
   (``courier.group_refusal`` vazio). Em preparo nunca vem marcado: a casa não sabe a
   hora em que fica pronto.
2. **Desvio:** o percurso junto (loja → paradas, na ordem de ``courier._route``) passa
   da maior perna sozinha em no máximo ``detour_km`` E em no máximo 40% dela.
   Agrupamento guloso pela hora em que ficou pronto, até ``courier.MAX_RIDE_STOPS``; o
   que sobra vira a próxima sugestão.
3. **Prazo:** o cliente que mais espera a mais espera no máximo ``extra_wait_minutes``.
4. **Preço:** a sugestão só vem MARCADA quando todas as cotações existem (a da corrida
   junta e a de cada pedido sozinho), a economia é de pelo menos ``saving_min_q`` E de
   ``saving_min_percent``, e a trava de sanidade passa (o km junto não é menor que o
   maior km sozinho). Sem cotação a sugestão aparece desmarcada (o operador monta se
   quiser); cotada e sem economia, não aparece: dinheiro da casa falha fechado.
5. **Freio:** cache de 60 s, no máximo 3 sugestões, nunca no selo do menu nem no push.

Os quatro parâmetros moram em ``Shop.defaults["delivery"]["ride_suggestion"]`` (Admin →
Pedido e entrega), declarados em ``docs/reference/data-schemas.md``. São palpites até o
B.I. medir.

O plano já nasce com o serviço que leva a corrida (``service``, ``service_reason``,
``service_options``), o contrato com a frente M3 (DEV-2026-030, #2526): a sugestão de
serviço é o padrão do Admin (``DeliveryService.is_default``).
"""

from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import asdict, dataclass

from django.core.cache import cache
from shopman.orderman.models import Order

logger = logging.getLogger(__name__)

#: Os palpites iniciais do dono (16/11/2026), valendo enquanto o Admin não grava outro.
DEFAULT_DETOUR_KM = 2.5
DEFAULT_SAVING_MIN_Q = 300
DEFAULT_SAVING_MIN_PERCENT = 15
DEFAULT_EXTRA_WAIT_MINUTES = 10
#: O desvio também não passa desta fração da maior perna sozinha (pontas opostas do
#: mesmo bairro não viram par só porque o bairro é pequeno).
DETOUR_SHARE = 0.40
#: Quantas sugestões a tela mostra de uma vez.
MAX_SUGGESTIONS = 3
#: Converte desvio em minutos de espera: moto na cidade (km/h) e o tempo de cada parada
#: antes (min). Palpites, como os parâmetros, até o B.I. medir.
SPEED_KMH = 20.0
STOP_MINUTES = 2.0
CACHE_SECONDS = 60


@dataclass(frozen=True)
class Candidate:
    """Um pedido que pode entrar numa sugestão: o ref, o ponto e quando ficou pronto."""

    ref: str
    latitude: float
    longitude: float
    ready_key: float = 0.0


@dataclass(frozen=True)
class Group:
    """Uma corrida possível, só pela geografia: as paradas na ordem do percurso."""

    refs: tuple[str, ...]
    detour_km: float
    #: Quem mais espera a mais, e quantos minutos (arredondado, nunca menos de 1).
    late_ref: str
    late_minutes: int


def params(shop=None) -> dict:
    """Os parâmetros da sugestão: os do Admin sobre os palpites iniciais."""
    if shop is None:
        from shopman.shop.models import Shop

        shop = Shop.load()
    defaults = getattr(shop, "defaults", None) or {}
    delivery = defaults.get("delivery") if isinstance(defaults.get("delivery"), dict) else {}
    stored = delivery.get("ride_suggestion") if isinstance(delivery.get("ride_suggestion"), dict) else {}
    def number(key: str, default):
        value = stored.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            return default
        return type(default)(value)

    return {
        "detour_km": number("detour_km", DEFAULT_DETOUR_KM),
        "saving_min_q": number("saving_min_q", DEFAULT_SAVING_MIN_Q),
        "saving_min_percent": number("saving_min_percent", DEFAULT_SAVING_MIN_PERCENT),
        "extra_wait_minutes": number("extra_wait_minutes", DEFAULT_EXTRA_WAIT_MINUTES),
    }


def km_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distância em linha reta (haversine), em km."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def route(origin: tuple[float, float], stops: list[Candidate]) -> list[Candidate]:
    """A ordem do percurso: o vizinho mais perto, a partir da loja (o mesmo de ``courier._route``)."""
    left, ordered, here = list(stops), [], origin
    while left:
        nearest = min(left, key=lambda stop: (stop.latitude - here[0]) ** 2 + (stop.longitude - here[1]) ** 2)
        left.remove(nearest)
        ordered.append(nearest)
        here = (nearest.latitude, nearest.longitude)
    return ordered


def measure(origin: tuple[float, float], stops: list[Candidate]) -> Group:
    """O desvio e a espera a mais de uma corrida com estas paradas."""
    ordered = route(origin, stops)
    along, here = 0.0, origin
    longest_solo = 0.0
    late_ref, late_minutes = ordered[0].ref, 0.0
    for index, stop in enumerate(ordered):
        point = (stop.latitude, stop.longitude)
        along += km_between(here, point)
        here = point
        solo = km_between(origin, point)
        longest_solo = max(longest_solo, solo)
        extra = (along - solo) / SPEED_KMH * 60 + STOP_MINUTES * index
        if extra >= late_minutes:
            late_ref, late_minutes = stop.ref, extra
    return Group(
        refs=tuple(stop.ref for stop in ordered),
        detour_km=max(0.0, along - longest_solo),
        late_ref=late_ref,
        late_minutes=max(1, round(late_minutes)) if len(ordered) > 1 else 0,
    )


def _fits(origin, stops: list[Candidate], settings: dict) -> Group | None:
    group = measure(origin, stops)
    longest = max(km_between(origin, (stop.latitude, stop.longitude)) for stop in stops)
    if group.detour_km > settings["detour_km"] or group.detour_km > DETOUR_SHARE * longest:
        return None
    if group.late_minutes > settings["extra_wait_minutes"]:
        return None
    return group


def plan_groups(origin: tuple[float, float], candidates: list[Candidate], settings: dict, *,
                max_stops: int) -> list[Group]:
    """A partição gulosa: o pronto há mais tempo puxa quem cabe com ele; o resto, a próxima.

    Só grupos de dois ou mais. Pura (sem banco): a régua é testável à mão.
    """
    pool = sorted(candidates, key=lambda candidate: candidate.ready_key)
    groups: list[Group] = []
    while pool:
        seed = pool.pop(0)
        chosen, best = [seed], None
        for other in list(pool):
            if len(chosen) >= max_stops:
                break
            fitted = _fits(origin, [*chosen, other], settings)
            if fitted is None:
                continue
            chosen.append(other)
            pool.remove(other)
            best = fitted
        if best is not None:
            groups.append(best)
    return groups


def _point(order) -> tuple[float, float] | None:
    address = (order.data or {}).get("delivery_address_structured") or {}
    try:
        return float(address["latitude"]), float(address["longitude"])
    except (KeyError, TypeError, ValueError):
        return None


def _ready_key(order) -> float:
    moment = order.ready_at or order.created_at
    return moment.timestamp() if moment else 0.0


def candidates_from(waiting, *, tasks: dict | None = None) -> list:
    """Os pedidos que podem entrar numa sugestão, entre os que esperam entregador.

    ``tasks``: as tarefas de despacho já lidas em lote (``courier.dispatch_tasks_for``),
    para a página não pagar uma consulta por pedido.
    """
    from shopman.shop.services import courier

    return [order for order in waiting
            if order.status == Order.Status.READY and _point(order) is not None
            and not courier.group_refusal(order, tasks=tasks)]


def waiting_pool() -> list:
    """As entregas prontas esperando entregador, para quem não tem a lista à mão (Painel)."""
    from shopman.shop.services import courier
    from shopman.shop.services.pos_sales_mode import is_pos_counter_order

    return [order for order in Order.objects.filter(status=Order.Status.READY).order_by("created_at")
            if courier.house_dispatches(order) and not is_pos_counter_order(order)
            and not courier.has_active_ride(order)]


def _service() -> dict:
    """O serviço que a sugestão propõe: o padrão do Admin, e as outras opções ativas."""
    from shopman.shop.models.delivery_service import DeliveryService

    options = [
        {"ref": service.ref, "name": service.name, "kind": service.kind, "is_default": service.is_default}
        for service in DeliveryService.objects.filter(is_active=True)
    ]
    default = next((option for option in options if option["is_default"]), None)
    return {
        "service": default["ref"] if default else "",
        "service_reason": "default" if default else "",
        "service_options": options,
    }


def _quote(group: Group, by_ref: dict, settings: dict) -> dict:
    """A cotação da sugestão e o veredito de preço (só marca com tudo cotado e economia)."""
    from shopman.shop.services import courier

    orders = [by_ref[ref] for ref in group.refs]
    together = courier.estimate_for_ride(orders)
    solos = [courier.estimate_for_order(order) for order in orders]
    quoted = bool(together) and all(solo and isinstance(solo.get("value_q"), int) for solo in solos)
    if not quoted:
        return {"quoted": False, "suggested": False, "together": None, "separate_q": None, "saving_q": None,
                "refs": list(group.refs)}
    separate_q = sum(int(solo["value_q"]) for solo in solos)
    saving_q = separate_q - int(together["value_q"])
    sane = float(together.get("km") or 0) >= max(float(solo.get("km") or 0) for solo in solos)
    suggested = (sane and saving_q >= settings["saving_min_q"]
                 and saving_q * 100 >= settings["saving_min_percent"] * separate_q)
    refs = [ref for ref in (together.get("stops") or []) if ref in by_ref]
    return {
        "quoted": True,
        "suggested": suggested,
        "together": {key: together[key] for key in ("value_q", "minutes", "km", "with_return") if key in together},
        "separate_q": separate_q,
        "saving_q": saving_q,
        "refs": refs if sorted(refs) == sorted(group.refs) else list(group.refs),
    }


def _cache_key(candidates, settings: dict) -> str:
    from shopman.shop.services import courier

    raw = "|".join(sorted(f"{order.ref}:{courier.dispatch_revision(order)}" for order in candidates))
    raw += "|" + ",".join(f"{key}={settings[key]}" for key in sorted(settings))
    return "courier:ride-plan:" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def ride_plan(waiting, *, quote: bool = True, tasks: dict | None = None) -> dict:
    """O plano das corridas para estes pedidos esperando entregador.

    ``suggestions``: até 3, na ordem da partição, cada uma com ``refs`` (ordem do
    percurso; a da cotação quando ela veio), ``codes``, ``late_ref``/``late_code`` e
    ``late_minutes``, ``quoted``, ``suggested`` (vem marcada), e com cotação
    ``together`` ``{value_q, minutes, km, with_return}``, ``separate_q`` e ``saving_q``.
    Cotada e sem a economia mínima, a sugestão sai do plano. ``quote=False`` devolve só
    a geografia (sem perguntar à central); ``tasks``, as tarefas de despacho em lote. Mais ``service``, ``service_reason`` e
    ``service_options``. Cache de 60 s pelos pedidos e as revisões deles.
    """
    from shopman.shop.models import Shop
    from shopman.shop.services import courier, delivery_services
    from shopman.shop.services.operator_orders import short_ref

    empty = {"suggestions": [], **_service()}
    shop = Shop.load()
    if shop is None or shop.latitude is None or shop.longitude is None or delivery_services.courier_backend() is None:
        return empty
    candidates = candidates_from(waiting, tasks=tasks)
    if len(candidates) < 2:
        return empty
    settings = params(shop)
    key = _cache_key(candidates, settings) + (":q" if quote else ":g")
    cached = cache.get(key)
    if cached is not None:
        return cached
    origin = (float(shop.latitude), float(shop.longitude))
    by_ref = {order.ref: order for order in candidates}
    groups = plan_groups(
        origin,
        [Candidate(order.ref, *_point(order), ready_key=_ready_key(order)) for order in candidates],
        settings,
        max_stops=courier.MAX_RIDE_STOPS,
    )
    suggestions = []
    for group in groups:
        if len(suggestions) >= MAX_SUGGESTIONS:
            break
        priced = _quote(group, by_ref, settings) if quote else {
            "quoted": False, "suggested": False, "together": None, "separate_q": None, "saving_q": None,
            "refs": list(group.refs)}
        if priced["quoted"] and not priced["suggested"]:
            # Cotada e sem economia (ou a cotação não passou na trava): não é sugestão.
            continue
        suggestions.append({
            **asdict(group),
            **priced,
            "key": "+".join(sorted(group.refs)),
            "codes": [short_ref(ref) for ref in priced["refs"]],
            "late_code": short_ref(group.late_ref),
            "detour_km": round(group.detour_km, 2),
        })
    plan = {"suggestions": suggestions, **_service()}
    cache.set(key, plan, CACHE_SECONDS)
    return plan


def suggestion_for(order, plan: dict) -> dict | None:
    """A sugestão do plano em que este pedido está, ou None."""
    return next((item for item in plan.get("suggestions") or [] if order.ref in item["refs"]), None)
