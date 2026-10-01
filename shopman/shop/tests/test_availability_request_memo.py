"""Disponibilidade calculada uma vez por request (GET), e nunca lida de antes de uma escrita.

Num GET da loja com sacola, o cardápio, as linhas da sacola e os portões do
trilho de sugestão perguntam ao Stockman pelos mesmos SKUs, no mesmo canal e na
mesma data. O memo de estoque do request (``request_memo.stock_reads_scope``)
guarda cada leitura por (recorte do canal, hoje, data, SKU): quem pergunta
depois recebe o que já foi lido e só lê o que falta.

O que estes testes travam:

- **mesma resposta**: dentro do memo, cada pergunta devolve exatamente o que a
  leitura direta devolveria, com a fila ligada e desligada, para subconjuntos
  e ordens diferentes de SKUs (é a premissa provada no F3: a leitura de um SKU
  não depende dos outros SKUs do lote);
- **mutação nunca lê dado velho**: qualquer escrita SQL no request esvazia e
  desliga o memo, inclusive ``QuerySet.update()`` e escrita desfeita por
  rollback; e request que muta (PUT, POST...) nem abre o memo;
- **cópias**: quem recebe pode mexer no ``dict`` sem envenenar o memo;
- **holds da sessão**: a leitura do Stockman é a de todo mundo; o desconto do
  hold da própria sessão é por sessão.
"""

from __future__ import annotations

import copy
from decimal import Decimal

import pytest
from django.db import connection, transaction
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from shopman.stockman.models import Hold, HoldStatus, Quant

from shopman.shop import request_memo
from shopman.shop.projections import catalog_context
from shopman.shop.services import availability as availability_service
from shopman.shop.services import waitlist
from shopman.shop.tests import test_catalog_availability_single_read as single_read
from shopman.shop.tests.test_catalog_availability_single_read import SKUS, _canonical

pytestmark = pytest.mark.django_db

#: O cenário do F3 (fila em três datas, lote vencendo, não conforme, pausado,
#: esgotado, bundle): o mesmo de ``test_catalog_availability_single_read``.
scenario = single_read.scenario


class _GetScope:
    """O que o ``RequestMemoMiddleware`` abre num GET."""

    def __enter__(self):
        self._memo = request_memo.request_memo_scope()
        self._stock = request_memo.stock_reads_scope()
        self._memo.__enter__()
        self._stock.__enter__()
        return self

    def __exit__(self, *exc):
        self._stock.__exit__(*exc)
        self._memo.__exit__(*exc)
        return False


def _stock_reads(ctx) -> list[str]:
    """A materialização de ``Quant`` com posição: uma por leitura do Stockman."""
    return [q["sql"] for q in ctx.captured_queries if "stockman_quant" in q["sql"] and "position" in q["sql"]]


def _stockman_queries(ctx) -> list[str]:
    return [q["sql"] for q in ctx.captured_queries if "stockman_" in q["sql"]]


def _today_available(sku: str) -> Decimal:
    return Decimal(str(catalog_context.availability_for_skus([sku], channel_ref="web")[sku]["available"]))


# ── Mesma resposta ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("scenario", [True, False], indirect=True, ids=["fila-ligada", "fila-desligada"])
class TestTheMemoAnswersWhatTheDirectReadAnswers:
    SUBSETS = (
        ["FILA-PAO"],
        ["FILA-CROI", "FILA-BOLO"],
        list(reversed(SKUS)),
        ["FILA-ESGOTADO", "FILA-PAUSADO", "FILA-SEM", "FILA-NAO-EXISTE"],
    )

    def test_catalog_then_cart_and_suggestion_subsets(self, scenario):
        direct = {
            tuple(subset): _canonical(catalog_context.availability_for_skus(subset, channel_ref="web"))
            for subset in (SKUS, *self.SUBSETS)
        }
        with _GetScope():
            for subset in (SKUS, *self.SUBSETS):
                memo = catalog_context.availability_for_skus(subset, channel_ref="web")
                assert _canonical(memo) == direct[tuple(subset)], subset

    def test_cart_first_then_the_catalog(self, scenario):
        """Ordem inversa: o primeiro chamador lê pouco, o segundo só o que falta."""
        direct = _canonical(catalog_context.availability_for_skus(SKUS, channel_ref="web"))
        with _GetScope():
            catalog_context.availability_for_skus(["FILA-PAO"], channel_ref="web")
            assert _canonical(catalog_context.availability_for_skus(SKUS, channel_ref="web")) == direct

    def test_dated_read_waitlist_and_bundle(self, scenario):
        today = scenario
        direct_dated = _canonical(catalog_context.availability_for_skus(SKUS, channel_ref="web", target_date=today))
        direct_next = _canonical(waitlist.next_batch_availability_for_skus(SKUS, channel_ref="web"))
        direct_bundle = catalog_context.bundle_availability_for_skus(["FILA-CESTA"], channel_ref="web")
        with _GetScope():
            catalog_context.availability_for_skus(SKUS[:3], channel_ref="web")
            assert (
                _canonical(catalog_context.availability_for_skus(SKUS, channel_ref="web", target_date=today))
                == direct_dated
            )
            assert _canonical(waitlist.next_batch_availability_for_skus(SKUS, channel_ref="web")) == direct_next
            assert catalog_context.bundle_availability_for_skus(["FILA-CESTA"], channel_ref="web") == direct_bundle

    def test_warm_read_changes_no_answer(self, scenario):
        cart, candidates = ["FILA-PAO", "FILA-BOLO"], ["FILA-CROI", "FILA-ESGOTADO"]
        direct_cart = _canonical(catalog_context.availability_for_skus(cart, channel_ref="web"))
        direct_candidates = _canonical(catalog_context.availability_for_skus(candidates, channel_ref="web"))
        with _GetScope():
            catalog_context.warm_availability_for_skus([*candidates, *cart], channel_ref="web")
            with CaptureQueriesContext(connection) as ctx:
                assert _canonical(catalog_context.availability_for_skus(candidates, channel_ref="web")) == (
                    direct_candidates
                )
                assert _canonical(catalog_context.availability_for_skus(cart, channel_ref="web")) == direct_cart
        assert _stockman_queries(ctx) == []


# ── Custo ─────────────────────────────────────────────────────────────────────


class TestEachSkuIsReadOncePerRequest:
    def test_repeated_question_does_not_go_to_the_stockman(self, scenario):
        with _GetScope():
            catalog_context.availability_for_skus(SKUS, channel_ref="web")
            with CaptureQueriesContext(connection) as ctx:
                catalog_context.availability_for_skus(["FILA-PAO", "FILA-BOLO"], channel_ref="web")
                catalog_context.availability_for_skus(SKUS, channel_ref="web")
        assert _stockman_queries(ctx) == []

    def test_only_the_missing_skus_are_read(self, scenario):
        with _GetScope():
            catalog_context.availability_for_skus(["FILA-PAO"], channel_ref="web")
            with CaptureQueriesContext(connection) as ctx:
                catalog_context.availability_for_skus(["FILA-PAO", "FILA-BOLO"], channel_ref="web")
        reads = _stock_reads(ctx)
        assert len(reads) == 1
        assert "FILA-BOLO" in reads[0]
        assert "FILA-PAO" not in reads[0]

    def test_without_the_scope_every_call_reads(self, scenario):
        assert request_memo.stock_bucket("x") is None
        with CaptureQueriesContext(connection) as ctx:
            catalog_context.availability_for_skus(SKUS, channel_ref="web")
            catalog_context.availability_for_skus(SKUS, channel_ref="web")
        assert len(_stock_reads(ctx)) == 2

    def test_warm_read_outside_the_memo_reads_nothing(self, scenario):
        with CaptureQueriesContext(connection) as ctx:
            catalog_context.warm_availability_for_skus(SKUS, channel_ref="web")
        assert ctx.captured_queries == []


class TestTheMemoHandsOutCopies:
    def test_mutating_the_answer_does_not_leak(self, scenario):
        with _GetScope():
            first = catalog_context.availability_for_skus(["FILA-PAO"], channel_ref="web")["FILA-PAO"]
            snapshot = _canonical({"FILA-PAO": copy.deepcopy(first)})
            first["available"] = Decimal("999")
            first["breakdown"]["ready"] = Decimal("999")
            if first.get("positions"):
                first["positions"][0]["available"] = Decimal("999")
            again = catalog_context.availability_for_skus(["FILA-PAO"], channel_ref="web")
        assert _canonical(again) == snapshot


# ── Mutação nunca lê dado velho ───────────────────────────────────────────────


class TestAWriteInsideTheRequestIsSeen:
    def test_a_hold_created_mid_request_is_counted(self, scenario):
        before = _today_available("FILA-PAO")
        quant = Quant.objects.filter(sku="FILA-PAO", position__ref="vitrine", target_date__isnull=True).get()
        with _GetScope():
            assert _today_available("FILA-PAO") == before
            Hold.objects.create(
                sku="FILA-PAO", quant=quant, quantity=Decimal("3"), target_date=scenario,
                status=HoldStatus.PENDING, metadata={"reference": "outra-sessao"},
            )
            assert request_memo.stock_bucket("x") is None  # desligado até o fim do request
            assert _today_available("FILA-PAO") == before - 3
        assert _today_available("FILA-PAO") == before - 3

    def test_queryset_update_without_signal_is_seen(self, scenario):
        """``QuerySet.update()`` não dispara sinal; o memo desliga pelo SQL, não por sinal."""
        before = _today_available("FILA-PAO")
        with _GetScope():
            assert _today_available("FILA-PAO") == before
            released = Hold.objects.filter(
                sku="FILA-PAO", target_date=scenario, status=HoldStatus.PENDING,
            ).update(status=HoldStatus.RELEASED)
            assert released == 1
            assert _today_available("FILA-PAO") == before + 2

    def test_a_rolled_back_write_leaves_nothing_behind(self, scenario):
        before = _today_available("FILA-PAO")
        quant = Quant.objects.filter(sku="FILA-PAO", position__ref="vitrine", target_date__isnull=True).get()
        with _GetScope():
            assert _today_available("FILA-PAO") == before
            with pytest.raises(RuntimeError), transaction.atomic():
                Hold.objects.create(
                    sku="FILA-PAO", quant=quant, quantity=Decimal("3"), target_date=scenario,
                    status=HoldStatus.PENDING, metadata={"reference": "outra-sessao"},
                )
                assert _today_available("FILA-PAO") == before - 3
                raise RuntimeError("desfaz")
            assert _today_available("FILA-PAO") == before

    def test_reads_only_is_not_a_write(self, scenario):
        with _GetScope():
            catalog_context.availability_for_skus(SKUS, channel_ref="web")
            with transaction.atomic():
                list(Quant.objects.select_for_update().filter(sku="FILA-PAO"))
            assert request_memo.stock_bucket("x") is not None


class TestOnlySafeMethodsOpenTheMemo:
    @pytest.mark.parametrize(
        ("method", "active"),
        [("get", True), ("head", True), ("put", False), ("post", False), ("patch", False), ("delete", False)],
    )
    def test_middleware(self, method, active):
        seen = {}

        def view(request):
            seen["active"] = request_memo.stock_reads_active()
            return "ok"

        middleware = request_memo.RequestMemoMiddleware(view)
        assert middleware(getattr(RequestFactory(), method)("/api/v1/cart/skus/X/")) == "ok"
        assert seen["active"] is active
        assert request_memo.stock_reads_active() is False


class TestOwnHoldsAreBySession:
    def test_two_sessions_in_the_same_request(self, scenario):
        quant = Quant.objects.filter(sku="FILA-PAO", position__ref="vitrine", target_date__isnull=True).get()
        for reference, qty in (("sessao-a", "1"), ("sessao-b", "3")):
            Hold.objects.create(
                sku="FILA-PAO", quant=quant, quantity=Decimal(qty), target_date=scenario,
                status=HoldStatus.PENDING, metadata={"reference": reference},
            )
        with _GetScope():
            for _ in range(2):
                assert availability_service.own_holds_by_sku("sessao-a", ["FILA-PAO", "FILA-BOLO"]) == {
                    "FILA-PAO": Decimal("1")
                }
                assert availability_service.own_holds_by_sku("sessao-b", ["FILA-PAO"]) == {"FILA-PAO": Decimal("3")}
            with CaptureQueriesContext(connection) as ctx:
                availability_service.own_holds_by_sku("sessao-a", ["FILA-BOLO", "FILA-PAO"])
        assert ctx.captured_queries == []
