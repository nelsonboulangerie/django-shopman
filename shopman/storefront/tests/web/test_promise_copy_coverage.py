"""Guardrail de cobertura da promessa: obrigação é conceito, não slot.

O acompanhamento não tem mais campo separado de "próximo passo" e "como
resolver" — cada estado fala UMA frase que já cobre o que o cliente precisa
saber. Para que a naturalidade não custe informação, este teste compara o que
a copy DECLARA cobrir (``_PROMISE_COVERS``) com as obrigações que o estado
declara no dado (ação pendente, prazo com consequência, aviso ativo).

O contrato é propositalmente insensível ao texto: a copy pode ser reescrita à
vontade sem quebrar teste. O que quebra é um estado ganhar obrigação nova e a
copy não assumir a cobertura.
"""
from __future__ import annotations

import pytest

from shopman.shop.projections.order_tracking import TrackingPromiseData
from shopman.storefront.presentation.order_tracking import (
    _PROMISE_COVERS,
    CONSEQUENCE,
    NEXT_STEP,
    NOTIFICATION,
    promise_obligations,
)
from shopman.shop.projections.types import Action


def _action(ref: str = "pay_now") -> Action:
    return Action(ref=ref, kind="link", label="Pagar agora", priority="primary", enabled=True)


def _data(state: str, **overrides) -> TrackingPromiseData:
    """TrackingPromiseData com o mínimo — só o que a obrigação depende varia."""
    fields = {
        "state": state,
        "tone": "info",
        "deadline_at": None,
        "deadline_kind": None,
        "timer_mode": "none",
        "deadline_action": "none",
        "requires_active_notification": False,
        "notification_topic": None,
    }
    fields.update(overrides)
    return TrackingPromiseData(**fields)


class TestObligationsDerivation:
    def test_pending_customer_action_is_a_next_step(self):
        data = _data("payment_requested", actions=(_action(),))

        assert NEXT_STEP in promise_obligations(data)

    def test_deadline_with_action_is_a_consequence(self):
        data = _data("payment_requested", deadline_action="show_payment_expired")

        assert CONSEQUENCE in promise_obligations(data)

    def test_deadline_action_none_is_not_a_consequence(self):
        data = _data("preparing", deadline_action="none")

        assert CONSEQUENCE not in promise_obligations(data)

    def test_active_notification_is_an_obligation(self):
        data = _data("payment_requested", requires_active_notification=True)

        assert NOTIFICATION in promise_obligations(data)

    def test_terminal_state_never_owes_a_notification(self):
        """Pedido terminal não tem o que avisar — prometer aviso ali é ruído."""
        data = _data("payment_expired", requires_active_notification=True)

        assert NOTIFICATION not in promise_obligations(data)


class TestCopyCoversObligations:
    """Cada estado do caminho felizcobre o que promete."""

    @pytest.mark.parametrize(
        ("state", "kwargs"),
        [
            ("received", {}),
            ("availability_check", {}),
            ("payment_confirmed", {}),
            ("preparing", {}),
            ("ready_delivery", {}),
            ("ready_pickup", {"actions": (_action("pickup"),)}),
            (
                "payment_requested",
                {
                    "actions": (_action(),),
                    "deadline_action": "show_payment_expired",
                    "requires_active_notification": True,
                },
            ),
            ("payment_pending", {"actions": (_action(),), "deadline_action": "show_payment_expired"}),
            ("dispatched", {"actions": (_action("confirm_received"),), "requires_active_notification": True}),
            ("delivered", {}),
            ("completed", {}),
        ],
    )
    def test_declared_coverage_satisfies_obligations(self, state, kwargs):
        data = _data(state, **kwargs)

        obligations = promise_obligations(data)
        covered = _PROMISE_COVERS[state]

        missing = obligations - covered
        assert not missing, f"{state} deve a copy: {sorted(missing)}"

    def test_every_known_state_declares_coverage(self):
        """Estado novo sem entrada em _PROMISE_COVERS é copy sem dono."""
        from shopman.storefront.presentation.order_tracking import _TERMINAL_PROMISE_COPY

        for state in _TERMINAL_PROMISE_COPY:
            assert state in _PROMISE_COVERS, state


class TestFootnoteStaysExceptional:
    """A nota de rodapé é exceção, não um segundo campo a preencher.

    Ela existe para tirar da frase principal a consequência que o cliente não
    precisa ler primeiro. Se todo estado ganhar uma, viramos o slot de volta —
    só que sem rótulo.
    """

    def test_footnote_only_where_there_is_a_consequence(self):
        from shopman.storefront.presentation.order_tracking import _PROMISE_FOOTNOTE

        for state in _PROMISE_FOOTNOTE:
            assert CONSEQUENCE in _PROMISE_COVERS[state], (
                f"{state} tem nota de rodapé sem declarar consequência — "
                "a nota não é lugar para informação solta."
            )

    def test_most_states_have_no_footnote(self):
        from shopman.storefront.presentation.order_tracking import _PROMISE_FOOTNOTE

        assert len(_PROMISE_FOOTNOTE) * 3 < len(_PROMISE_COVERS), (
            "nota de rodapé deixou de ser exceção: "
            f"{len(_PROMISE_FOOTNOTE)} de {len(_PROMISE_COVERS)} estados."
        )
