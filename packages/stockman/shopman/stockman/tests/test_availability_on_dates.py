"""
Equivalência: uma varredura para várias datas ≡ uma leitura inteira por data.

``availability_for_skus_on_dates`` lê as linhas de ``Quant`` uma vez, até a
maior data, e recorta cada data em Python. A fila de espera e o cardápio
passaram a perguntar "hoje e as próximas fornadas" por ela, em vez de chamar
``availability_for_skus`` de novo para cada data candidata — e cada chamada
materializava todas as linhas de estoque outra vez (o custo é O(linhas), não
SQL).

O oráculo é ``_reference_availability_for_skus``: a implementação de
``availability_for_skus`` ANTES da mudança, copiada sem alteração (só o
nome). Ela fica congelada aqui de propósito: é a régua contra a qual a leitura
nova é medida, campo a campo, para toda combinação de recorte de canal e para
datas no passado, hoje, nas fornadas e depois delas.

O cenário cobre o que muda com a data: estoque de hoje, fornadas futuras,
lote que vence no meio do intervalo (com e sem margem), validade de
prateleira (0 e 3 dias, contada pela criação ou pela fornada), holds ativos,
vencidos e liberados, lote ``started``, posição de processo e não vendável,
qualidade (allowlist, não conforme, lote nomeado sem ``Batch``), SKU pausado
com estoque, SKU esgotado (quant zerado continua rastreado) e SKU sem estoque.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from itertools import product as cartesian

import pytest
from django.db.models import Q, Sum
from django.utils import timezone
from shopman.stockman.adapters.sku_validation import get_sku_validator, reset_sku_validator
from shopman.stockman.models import Batch, Hold, Position, PositionKind, Quant
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.protocols.sku import SkuInfo, SkuValidationResult
from shopman.stockman.services.availability import (
    STARTED_BATCH,
    _build_availability_dict,
    _zero_availability_dict,
    availability_for_skus,
    availability_for_skus_on_dates,
)

pytestmark = pytest.mark.django_db


# ── O oráculo: availability_for_skus como era antes (cópia literal) ──────────


def _reference_availability_for_skus(
    skus: list[str],
    safety_margin: int = 0,
    *,
    target_date: date | None = None,
    allowed_positions: list[str] | None = None,
    excluded_positions: list[str] | None = None,
    expiry_margin_days: int = 0,
    include_nonconforming: bool = True,
    allowed_quality_grade_refs: list[str] | tuple[str, ...] | None = None,
) -> dict[str, dict]:
    """
    Batch version of availability_for_sku() — same logic, few queries regardless of N.

    Returns {sku: availability_dict} for all requested SKUs. Functionally
    identical to calling availability_for_sku() per SKU: shares the canonical
    scope gate (shelflife, batch expiry + margin, batch conformity, position
    allow/deny, target_date) via per-SKU Python filtering on top of a bulk
    quant fetch.
    """
    from types import SimpleNamespace

    from shopman.stockman.models import Batch
    from shopman.stockman.shelflife import is_valid_for_date

    if not skus:
        return {}

    zero = Decimal("0")

    today = timezone.localdate()
    target = target_date or today

    # ── Query 1: orderable SKUs from the offering contract ───────────────────
    validator = get_sku_validator()
    validations = validator.validate_skus(skus)
    sku_infos = validator.get_sku_infos(skus)
    orderable_skus: set[str] = {
        sku
        for sku, validation in validations.items()
        if validation.valid and validation.is_published and validation.is_sellable
    }
    shelflife_by_sku: dict[str, int | None] = {
        sku: (info.shelflife_days if info is not None else None) for sku, info in sku_infos.items()
    }

    # ── Query 2: excluded batch refs grouped by SKU ───────────────────────────
    # Expiry honors the channel's near-expiry margin (0 = only already
    # expired); conformity mirrors quants_eligible_for — the frozen markdown,
    # never an informational reason, drives the compatibility gate.
    expiry_cutoff = target + timedelta(days=max(0, expiry_margin_days))
    expired_refs_by_sku: dict[str, set[str]] = {}
    for row in Batch.objects.filter(sku__in=skus, expiry_date__lt=expiry_cutoff).values("sku", "ref"):
        expired_refs_by_sku.setdefault(row["sku"], set()).add(row["ref"])
    allowed_batch_refs_by_sku: dict[str, set[str]] | None = None
    if allowed_quality_grade_refs is not None:
        allowed_refs = tuple(allowed_quality_grade_refs)
        allowed_batch_refs_by_sku = {}
        for row in Batch.objects.filter(
            sku__in=skus,
            quality_grade_ref__in=allowed_refs,
        ).values("sku", "ref"):
            allowed_batch_refs_by_sku.setdefault(row["sku"], set()).add(row["ref"])
    elif not include_nonconforming:
        for row in Batch.objects.filter(sku__in=skus).nonconforming().values("sku", "ref"):
            expired_refs_by_sku.setdefault(row["sku"], set()).add(row["ref"])

    # ── Query 3: planned SKUs (has future quants) ─────────────────────────────
    planned_skus: set[str] = set(
        Quant.objects.filter(
            sku__in=skus,
            target_date__gt=today,
            target_date__lte=target,
            _quantity__gt=0,
        )
        .values_list("sku", flat=True)
        .distinct()
    )

    # ── Query 3b: which SKUs have ANY Quant at all (scope-independent) ────────
    tracked_skus: set[str] = set(Quant.objects.filter(sku__in=skus).values_list("sku", flat=True).distinct())

    # ── Query 4: physical quants (current/past), select_related position ──────
    quant_qs = (
        Quant.objects.filter(sku__in=skus)
        .filter(Q(target_date__isnull=True) | Q(target_date__lte=target))
        .filter(_quantity__gt=0)
        .select_related("position")
    )
    if allowed_positions is not None:
        quant_qs = quant_qs.filter(position__ref__in=allowed_positions)
    if excluded_positions:
        quant_qs = quant_qs.exclude(position__ref__in=excluded_positions)

    # Fetch all matching quants
    all_quants = list(quant_qs)

    # ── Batch held amounts: one query across all quant PKs ────────────────────
    quant_ids = [q.pk for q in all_quants]
    now = timezone.now()
    held_by_quant: dict[int, Decimal] = {}
    if quant_ids:
        rows = (
            Hold.objects.filter(
                quant_id__in=quant_ids,
                status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))
            .values("quant_id")
            .annotate(total=Sum("quantity"))
        )
        for row in rows:
            held_by_quant[row["quant_id"]] = row["total"] or zero

    # ── Group quants by SKU and compute breakdown ─────────────────────────────
    quants_by_sku: dict[str, list] = {}
    for q in all_quants:
        quants_by_sku.setdefault(q.sku, []).append(q)

    result: dict[str, dict] = {}

    for sku in skus:
        # Product paused: return zeros (stock may exist but not for sale)
        if sku not in orderable_skus:
            availability_policy = (
                sku_infos.get(sku).availability_policy if sku_infos.get(sku) is not None else "planned_ok"
            )
            result[sku] = _zero_availability_dict(
                sku,
                availability_policy,
                safety_margin,
                is_paused=True,
                is_tracked=(sku in tracked_skus),
            )
            continue

        expired_refs = expired_refs_by_sku.get(sku, set())
        is_planned = sku in planned_skus
        availability_policy = sku_infos.get(sku).availability_policy if sku_infos.get(sku) is not None else "planned_ok"

        ready = Decimal("0")
        in_production = Decimal("0")
        planned = Decimal("0")
        held_ready = Decimal("0")
        held_production = Decimal("0")
        held_planned = Decimal("0")
        positions_data = []

        shelflife_ns = SimpleNamespace(
            sku=sku,
            shelf_life_days=shelflife_by_sku.get(sku),
        )

        for quant in quants_by_sku.get(sku, []):
            if quant.batch and quant.batch in expired_refs:
                continue
            if (
                allowed_batch_refs_by_sku is not None
                and quant.batch
                and quant.batch not in allowed_batch_refs_by_sku.get(sku, set())
            ):
                # Named refs without a matching Batch are unclassified lots,
                # not batchless stock. Match the canonical queryset and the
                # fulfill recheck by failing them closed under an allowlist.
                continue
            if not is_valid_for_date(quant, shelflife_ns, target):
                continue

            qty = quant._quantity
            held = held_by_quant.get(quant.pk, zero)

            # Classify into breakdown buckets (same logic as availability_for_sku)
            if quant.batch == STARTED_BATCH:
                in_production += qty
                held_production += held
            elif quant.is_future:
                planned += qty
                held_planned += held
            elif quant.position and (quant.position.kind == "process" or not quant.position.is_saleable):
                in_production += qty
                held_production += held
            elif quant.position and quant.position.is_saleable:
                ready += qty
                held_ready += held

            if quant.position:
                positions_data.append(
                    {
                        "position_ref": quant.position.ref,
                        "position_name": quant.position.name,
                        "available": qty - held,
                        "reserved": held,
                        "batch": quant.batch or None,
                    }
                )

        result[sku] = _build_availability_dict(
            sku=sku,
            availability_policy=availability_policy,
            ready=ready,
            in_production=in_production,
            planned=planned,
            held_ready=held_ready,
            held_production=held_production,
            held_planned=held_planned,
            safety_margin=safety_margin,
            is_planned=is_planned,
            positions_data=positions_data,
            is_tracked=(sku in tracked_skus),
        )

    return result


# ── Catálogo de ofertas do cenário ────────────────────────────────────────────

_SHELF_LIFE = {"CROI": 0, "BOLO": 3}
_POLICY = {"SOB-DEMANDA": "demand_ok", "SO-ESTOQUE": "stock_only"}
_PAUSED = {"PAUSADO"}
_UNKNOWN = {"DESCONHECIDO"}

SKUS = [
    "PAO",
    "CROI",
    "BOLO",
    "QUAL",
    "PAUSADO",
    "ESGOTADO",
    "SOB-DEMANDA",
    "SO-ESTOQUE",
    "SEM-ESTOQUE",
    "DESCONHECIDO",
]


class MixedSkuValidator:
    """Validade, política e pausa por SKU — o que o Offerman diria de cada um."""

    def validate_sku(self, sku: str) -> SkuValidationResult:
        known = sku not in _UNKNOWN
        return SkuValidationResult(
            valid=known,
            sku=sku,
            product_name=sku if known else None,
            is_published=known,
            is_sellable=known and sku not in _PAUSED,
        )

    def validate_skus(self, skus: list[str]) -> dict[str, SkuValidationResult]:
        return {sku: self.validate_sku(sku) for sku in skus}

    def get_sku_info(self, sku: str) -> SkuInfo | None:
        if sku in _UNKNOWN:
            return None
        return SkuInfo(
            sku=sku,
            name=sku,
            description=None,
            is_published=True,
            is_sellable=sku not in _PAUSED,
            unit="un",
            category=None,
            base_price_q=None,
            availability_policy=_POLICY.get(sku, "planned_ok"),
            shelflife_days=_SHELF_LIFE.get(sku),
            metadata=None,
        )

    def get_sku_infos(self, skus: list[str]) -> dict[str, SkuInfo | None]:
        return {sku: self.get_sku_info(sku) for sku in skus}

    def search_skus(self, query: str, limit: int = 20, include_inactive: bool = False) -> list[SkuInfo]:
        return []


@pytest.fixture
def mixed_validator(settings):
    settings.STOCKMAN = {
        **getattr(settings, "STOCKMAN", {}),
        "SKU_VALIDATOR": "shopman.stockman.tests.test_availability_on_dates.MixedSkuValidator",
    }
    reset_sku_validator()
    yield
    reset_sku_validator()


@pytest.fixture
def today() -> date:
    return timezone.localdate()


@pytest.fixture
def scenario(mixed_validator, today):
    vitrine = Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)
    reserva = Position.objects.create(ref="reserva", name="Reserva", kind=PositionKind.PHYSICAL, is_saleable=True)
    deposito = Position.objects.create(ref="deposito", name="Depósito", kind=PositionKind.PHYSICAL, is_saleable=False)
    producao = Position.objects.create(ref="producao", name="Produção", kind=PositionKind.PROCESS)
    day = timedelta(days=1)

    def quant(sku, position, qty, *, target=None, batch="", created_days_ago=0):
        q = Quant.objects.create(
            sku=sku,
            position=position,
            target_date=target,
            batch=batch,
            _quantity=Decimal(qty),
        )
        if created_days_ago:
            Quant.objects.filter(pk=q.pk).update(created_at=timezone.now() - timedelta(days=created_days_ago))
        return q

    def hold(q, qty, status, *, expires_in_minutes=None):
        Hold.objects.create(
            sku=q.sku,
            quant=q,
            quantity=Decimal(qty),
            target_date=q.target_date or today,
            status=status,
            expires_at=(
                None if expires_in_minutes is None else timezone.now() + timedelta(minutes=expires_in_minutes)
            ),
            metadata={},
        )

    # PAO: pronto, não vendável, em produção (started), três fornadas futuras.
    pao_vitrine = quant("PAO", vitrine, "10")
    hold(pao_vitrine, "3", HoldStatus.PENDING)
    hold(pao_vitrine, "1", HoldStatus.CONFIRMED, expires_in_minutes=30)
    hold(pao_vitrine, "2", HoldStatus.PENDING, expires_in_minutes=-30)  # vencido: não conta
    hold(pao_vitrine, "4", HoldStatus.RELEASED)  # liberado: não conta
    quant("PAO", deposito, "4")
    quant("PAO", producao, "3", batch=STARTED_BATCH)
    pao_amanha = quant("PAO", vitrine, "6", target=today + day)
    hold(pao_amanha, "2", HoldStatus.PENDING)
    quant("PAO", vitrine, "5", target=today + 2 * day)
    quant("PAO", reserva, "2", target=today + 3 * day)

    # CROI: validade 0 — o de ontem não vale hoje; a fornada de amanhã está
    # toda reservada, a fila tem de pular para a de T+3.
    quant("CROI", vitrine, "8")
    quant("CROI", vitrine, "5", batch="ONTEM", created_days_ago=1)
    croi_amanha = quant("CROI", vitrine, "12", target=today + day)
    hold(croi_amanha, "12", HoldStatus.CONFIRMED)
    quant("CROI", vitrine, "7", target=today + 3 * day)

    # BOLO: validade 3 e lotes que vencem dentro do intervalo de datas.
    Batch.objects.create(sku="BOLO", ref="B-HOJE", expiry_date=today)
    Batch.objects.create(sku="BOLO", ref="B-AMANHA", expiry_date=today + day)
    Batch.objects.create(sku="BOLO", ref="B-T3", expiry_date=today + 3 * day)
    Batch.objects.create(sku="BOLO", ref="B-SEM")
    quant("BOLO", vitrine, "2", batch="B-HOJE")
    quant("BOLO", vitrine, "3", batch="B-AMANHA")
    quant("BOLO", vitrine, "4", batch="B-T3")
    quant("BOLO", vitrine, "5", batch="B-SEM")
    quant("BOLO", vitrine, "6", target=today + 2 * day, batch="B-T3")
    quant("BOLO", reserva, "1", created_days_ago=4)  # fora da validade de prateleira

    # QUAL: qualidade e conformidade do lote.
    Batch.objects.create(sku="QUAL", ref="Q-STD", quality_grade_ref="standard")
    Batch.objects.create(sku="QUAL", ref="Q-FAIR", quality_grade_ref="fair", nonconformity_percent=30)
    Batch.objects.create(sku="QUAL", ref="Q-NOME", quality_grade_ref="")
    quant("QUAL", vitrine, "1")
    quant("QUAL", vitrine, "2", batch="Q-STD")
    quant("QUAL", vitrine, "3", batch="Q-FAIR")
    quant("QUAL", vitrine, "4", batch="Q-NOME")
    quant("QUAL", vitrine, "5", batch="Q-ORFAO")  # lote nomeado sem Batch
    quant("QUAL", vitrine, "6", target=today + 2 * day, batch="Q-STD")
    quant("QUAL", deposito, "7", target=today + day, batch="Q-FAIR")

    # PAUSADO tem estoque, mas não está à venda; ESGOTADO vendeu tudo.
    quant("PAUSADO", vitrine, "9")
    quant("PAUSADO", vitrine, "3", target=today + day)
    quant("ESGOTADO", vitrine, "0")
    quant("SOB-DEMANDA", vitrine, "1")
    quant("SOB-DEMANDA", vitrine, "4", target=today + 2 * day)
    quant("SO-ESTOQUE", vitrine, "2")
    quant("SO-ESTOQUE", vitrine, "5", target=today + day)
    return today


def _dates(today: date) -> list[date]:
    return [today + timedelta(days=offset) for offset in (-1, 0, 1, 2, 3, 5)]


SCOPES = [
    {
        "safety_margin": safety_margin,
        "allowed_positions": allowed_positions,
        "excluded_positions": excluded_positions,
        "expiry_margin_days": expiry_margin_days,
        "include_nonconforming": include_nonconforming,
        "allowed_quality_grade_refs": allowed_quality_grade_refs,
    }
    for (
        safety_margin,
        allowed_positions,
        excluded_positions,
        expiry_margin_days,
        (include_nonconforming, allowed_quality_grade_refs),
    ) in cartesian(
        (0, 2),
        (None, ["vitrine", "reserva"]),
        (None, ["deposito"]),
        (0, 1),
        ((True, None), (False, None), (True, ("excellent", "standard"))),
    )
]


def _canonical(by_sku: dict[str, dict]) -> dict[str, dict]:
    """``positions`` sai na ordem do banco, sem ORDER BY nos dois lados: ordena."""
    out = {}
    for sku, info in by_sku.items():
        info = dict(info)
        info["positions"] = sorted(
            info["positions"],
            key=lambda p: (p["position_ref"], p["batch"] or "", p["available"], p["reserved"]),
        )
        out[sku] = info
    return out


class TestOneScanEqualsOneReadPerDate:
    @pytest.mark.parametrize("scope", SCOPES, ids=lambda s: "-".join(str(v) for v in s.values()))
    def test_every_date_matches_the_reference_field_by_field(self, scenario, scope):
        today = scenario
        dates = _dates(today)

        by_date = availability_for_skus_on_dates(SKUS, dates, **scope)

        assert list(by_date) == dates
        for target in dates:
            expected = _canonical(_reference_availability_for_skus(SKUS, target_date=target, **scope))
            assert _canonical(by_date[target]) == expected, target
            assert _canonical(availability_for_skus(SKUS, target_date=target, **scope)) == expected, target

    def test_default_target_is_today(self, scenario):
        assert _canonical(availability_for_skus(SKUS)) == _canonical(_reference_availability_for_skus(SKUS))

    def test_a_sku_answer_does_not_depend_on_the_other_skus_in_the_batch(self, scenario):
        """A fila lê todos os SKUs de uma vez e escolhe depois: isso só vale se
        a resposta de um SKU não muda com quem mais está no lote."""
        dates = _dates(scenario)
        everyone = availability_for_skus_on_dates(SKUS, dates)
        for sku in SKUS:
            alone = availability_for_skus_on_dates([sku], dates)
            for target in dates:
                assert _canonical(alone[target]) == _canonical({sku: everyone[target][sku]})

    def test_the_scenario_has_teeth(self, scenario):
        """O cenário muda de resposta entre datas e recortes — senão a
        equivalência acima seria trivial."""
        today = scenario
        day = timedelta(days=1)
        reference = _reference_availability_for_skus

        # Fornada de amanhã toda reservada; a de T+3 ainda tem as 7.
        assert reference(["CROI"], target_date=today + day)["CROI"]["planned"] == Decimal("0")
        assert reference(["CROI"], target_date=today + 3 * day)["CROI"]["planned"] == Decimal("7")
        # Validade de prateleira 0: o croissant de ontem não conta hoje.
        assert reference(["CROI"], target_date=today)["CROI"]["ready_physical"] == Decimal("8")
        # (o corte é só por baixo: a leitura de ontem ainda soma o de hoje)
        assert reference(["CROI"], target_date=today - day)["CROI"]["ready_physical"] == Decimal("13")
        # Lote que vence: a margem e a data mudam o pronto do bolo.
        bolo = [
            reference(["BOLO"], target_date=today + offset * day, expiry_margin_days=margin)["BOLO"]["ready_physical"]
            for offset, margin in ((0, 0), (0, 1), (1, 0), (3, 0))
        ]
        assert len(set(bolo)) > 1
        # PAO: holds ativos contam, vencidos e liberados não.
        pao = reference(["PAO"], target_date=today)["PAO"]
        assert pao["held_ready"] == Decimal("4")
        assert pao["is_planned"] is False
        assert reference(["PAO"], target_date=today + day)["PAO"]["is_planned"] is True
        # Esgotado continua rastreado; sem estoque, não.
        assert reference(["ESGOTADO"])["ESGOTADO"]["is_tracked"] is True
        assert reference(["SEM-ESTOQUE"])["SEM-ESTOQUE"]["is_tracked"] is False
        assert reference(["PAUSADO"])["PAUSADO"]["is_paused"] is True

    def test_more_dates_cost_no_more_queries(self, scenario):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        dates = _dates(scenario)
        with CaptureQueriesContext(connection) as one_date:
            availability_for_skus_on_dates(SKUS, [dates[-1]])
        with CaptureQueriesContext(connection) as all_dates:
            availability_for_skus_on_dates(SKUS, dates)

        assert len(all_dates.captured_queries) == len(one_date.captured_queries)

    def test_empty_inputs(self, scenario):
        today = scenario
        assert availability_for_skus([]) == {}
        assert availability_for_skus_on_dates([], [today]) == {today: {}}
        assert availability_for_skus_on_dates(SKUS, []) == {}
        twice = availability_for_skus_on_dates(SKUS, [today, today])
        assert list(twice) == [today]
