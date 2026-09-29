"""Activate checkout address-map confirmation for existing tenants.

The UI and the tenant-scoped kill switch shipped disabled in #1256/#1261.
Existing databases do not run the instance seed during a release, so activation
must travel through the audited release path.  This data migration changes only
``defaults.storefront.address_map_confirmation_enabled`` and preserves every
other tenant setting.

Rollback removes the key, which restores the fail-closed default (``False``)
without deleting the remaining ``storefront`` namespace.
"""

from copy import deepcopy

from django.db import migrations

FLAG = "address_map_confirmation_enabled"


def _storefront(defaults):
    raw = defaults.get("storefront")
    return deepcopy(raw) if isinstance(raw, dict) else {}


def forwards(apps, schema_editor):
    Shop = apps.get_model("shop", "Shop")
    updated = 0
    for shop in Shop.objects.all().iterator():
        defaults = deepcopy(shop.defaults) if isinstance(shop.defaults, dict) else {}
        storefront = _storefront(defaults)
        if storefront.get(FLAG) is True:
            continue
        storefront[FLAG] = True
        defaults["storefront"] = storefront
        shop.defaults = defaults
        shop.save(update_fields=["defaults"])
        updated += 1
    print(f"ADDRESS_MAP_ACTIVATION_OK updated_tenants={updated} final=true")


def backwards(apps, schema_editor):
    Shop = apps.get_model("shop", "Shop")
    updated = 0
    for shop in Shop.objects.all().iterator():
        defaults = deepcopy(shop.defaults) if isinstance(shop.defaults, dict) else {}
        storefront = _storefront(defaults)
        if FLAG not in storefront:
            continue
        storefront.pop(FLAG, None)
        if storefront:
            defaults["storefront"] = storefront
        else:
            defaults.pop("storefront", None)
        shop.defaults = defaults
        shop.save(update_fields=["defaults"])
        updated += 1
    print(f"ADDRESS_MAP_ROLLBACK_OK updated_tenants={updated} final=false")


class Migration(migrations.Migration):
    dependencies = [("shop", "0084_producao_concluida_no_marketing")]

    operations = [migrations.RunPython(forwards, backwards)]
