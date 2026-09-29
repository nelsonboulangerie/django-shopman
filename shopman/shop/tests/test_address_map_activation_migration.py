from copy import deepcopy
from importlib import import_module

import pytest
from django.apps import apps

MIGRATION = import_module("shopman.shop.migrations.0085_enable_checkout_address_map")
FLAG = "address_map_confirmation_enabled"


@pytest.mark.django_db
def test_address_map_activation_round_trip_preserves_every_other_tenant_default(shop):
    original = {
        "rules": {"minimum_order_q": 2500},
        "storefront": {
            "existing": "preserved",
            "nested": {"keep": True},
        },
    }
    shop.defaults = deepcopy(original)
    shop.save(update_fields=["defaults"])

    MIGRATION.forwards(apps, None)
    shop.refresh_from_db()
    assert shop.defaults == {
        **original,
        "storefront": {
            **original["storefront"],
            FLAG: True,
        },
    }

    MIGRATION.backwards(apps, None)
    shop.refresh_from_db()
    assert shop.defaults == original


@pytest.mark.django_db
def test_address_map_activation_is_idempotent_and_rollback_keeps_namespace(shop):
    shop.defaults = {"storefront": {"existing": "preserved", FLAG: True}}
    shop.save(update_fields=["defaults"])

    MIGRATION.forwards(apps, None)
    MIGRATION.forwards(apps, None)
    shop.refresh_from_db()
    assert shop.defaults["storefront"] == {"existing": "preserved", FLAG: True}

    MIGRATION.backwards(apps, None)
    MIGRATION.backwards(apps, None)
    shop.refresh_from_db()
    assert shop.defaults["storefront"] == {"existing": "preserved"}
