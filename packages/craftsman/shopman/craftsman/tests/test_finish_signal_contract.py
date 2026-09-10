"""Os dois fatos do Core em que a blindagem da cauda de ``production_changed`` se apoia.

Ambos vivem AQUI, no pacote, porque são contrato do ``CraftExecution`` — não do
orquestrador. O ``shop`` blinda a cauda cosmética justamente PORQUE estes dois
fatos são verdade:

1. ``production_changed`` é emitido com ``.send()`` (não ``.send_robust()``): a
   exceção de QUALQUER receiver propaga e aborta os posteriores + o caller. Um
   receiver frágil pode, sim, derrubar o ``finish`` de uma fornada já commitada.

2. No replay idempotente (mesma ``idempotency_key``) o ``finish`` devolve a WO
   existente ANTES do ``.send()`` — ou seja, NÃO reemite o sinal. Um receiver
   pulado uma vez não é refeito pelo retry do operador.

Juntos, os dois explicam por que um cosmético que estoura deixa efeito órfão
para sempre — e por que a cura tem de ser blindar a cauda (no ``shop``), não
trocar para ``.send_robust()`` (que engoliria também a perna de estoque, que
DEVE gritar).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.craftsman.signals import production_changed

pytestmark = pytest.mark.django_db


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="contract-croissant",
        name="Croissant",
        output_sku="croissant",
        batch_size=Decimal("10"),
    )


def test_send_propagates_a_receiver_error_out_of_finish(recipe):
    """Fato 1: ``.send()`` propaga — o receiver estoura, o ``finish`` estoura.

    E a WO fica commitada mesmo assim, porque o ``.send()`` é PÓS-commit: é este
    par (fornada correta no banco + erro na tela) que torna a cauda perigosa.
    """
    wo = craft.plan(recipe, 40)

    def _boom(sender, **kwargs):
        if kwargs.get("action") == "finished":
            raise RuntimeError("um receiver posterior estourou")

    production_changed.connect(_boom, dispatch_uid="contract-boom", weak=False)
    try:
        with pytest.raises(RuntimeError):
            craft.finish(wo, finished=40, expected_rev=0)
    finally:
        production_changed.disconnect(dispatch_uid="contract-boom")

    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.FINISHED  # commitada, apesar do erro


def test_idempotent_replay_does_not_re_emit_the_signal(recipe):
    """Fato 2: o replay devolve a WO existente ANTES do ``.send()``.

    Logo, quem foi pulado no primeiro ``finish`` não roda no retry — e é por isso
    que a cauda precisa nunca ser pulada por engano.
    """
    wo = craft.plan(recipe, 40)

    fired: list[str] = []

    def _spy(sender, **kwargs):
        if kwargs.get("action") == "finished":
            fired.append(kwargs.get("work_order").ref)

    production_changed.connect(_spy, dispatch_uid="contract-spy", weak=False)
    try:
        craft.finish(wo, finished=40, expected_rev=0, idempotency_key="same-key")
        assert fired == [wo.ref]

        # O operador aperta de novo com os mesmos dados: replay idempotente.
        result = craft.finish(wo, finished=40, idempotency_key="same-key")
        assert result.pk == wo.pk
        # O sinal NÃO foi reemitido — a cauda não é refeita pelo retry.
        assert fired == [wo.ref]
    finally:
        production_changed.disconnect(dispatch_uid="contract-spy")


def test_a_middle_receiver_error_starves_the_receivers_after_it(recipe):
    """A raiz do órfão: ``.send()`` para no PRIMEIRO que estoura.

    Um receiver do MEIO que estoura mata os posteriores — e, pelo Fato 2, o
    retry não os refaz. Este teste fixa o mecanismo que a blindagem do ``shop``
    neutraliza (lá, tornando a cauda incapaz de estourar).
    """
    wo = craft.plan(recipe, 40)
    order: list[str] = []

    def _early_boom(sender, **kwargs):
        if kwargs.get("action") == "finished":
            order.append("early")
            raise RuntimeError("cosmético estourou no meio")

    def _later(sender, **kwargs):
        if kwargs.get("action") == "finished":
            order.append("later")

    # Conexão define a ordem de dispatch: early antes de later.
    production_changed.connect(_early_boom, dispatch_uid="starve-early", weak=False)
    production_changed.connect(_later, dispatch_uid="starve-later", weak=False)
    try:
        with pytest.raises(RuntimeError):
            craft.finish(wo, finished=Decimal("40"), expected_rev=0)
        # O posterior nunca rodou: foi abortado pelo erro do anterior.
        assert order == ["early"]
    finally:
        production_changed.disconnect(dispatch_uid="starve-early")
        production_changed.disconnect(dispatch_uid="starve-later")
