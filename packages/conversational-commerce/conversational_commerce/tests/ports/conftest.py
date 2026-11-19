from __future__ import annotations

import pytest

from conversational_commerce.ports import TrustedContext
from conversational_commerce.testing.conformance.harness import HarnessEnv
from conversational_commerce.testing.fakes import FakeWorld


@pytest.fixture
def world() -> FakeWorld:
    return FakeWorld()


@pytest.fixture
def ctx() -> TrustedContext:
    return TrustedContext(tenant="tenant-a", environment="test", subject="customer-1")


@pytest.fixture
def env(world, ctx) -> HarnessEnv:
    return HarnessEnv(
        ctx=ctx,
        clock=world.clock,
        raw_message={"id": "provider-1", "from": "address-1", "content_ref": "text:hello"},
        item_ref="ITEM-A",
        cart_ref="cart-1",
        other_subject="customer-2",
        policy_id="returns",
        fresh_terms=lambda: world.commerce_read.quote(ctx, "cart-1"),
    )
