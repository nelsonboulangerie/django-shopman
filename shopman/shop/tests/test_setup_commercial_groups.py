from __future__ import annotations

from django.core.management import call_command
from shopman.guestman.models import PriceTier

from shopman.shop.models import Promotion


def test_setup_commercial_groups_installs_the_promised_defaults(db):
    call_command("setup_commercial_groups", verbosity=0)

    staff = PriceTier.objects.get(ref="staff")
    alliance = PriceTier.objects.get(ref="alianca-francesa")
    assert staff.name == "Equipe"
    assert staff.metadata == {
        "discount_kind": "equipe",
        "rounding": 50,
        "savings_message": "Hoje você economizou {amount} por ser da Equipe",
    }
    assert alliance.metadata["discount_kind"] == "parceiro"

    staff_discount = Promotion.objects.get(ref="grupo-staff")
    alliance_discount = Promotion.objects.get(ref="grupo-alianca-francesa")
    assert (staff_discount.type, staff_discount.value) == (Promotion.PERCENT, 30)
    assert staff_discount.customer_segments == ["staff"]
    assert staff_discount.fulfillment_types == ["pickup"]
    assert (alliance_discount.type, alliance_discount.value) == (Promotion.PERCENT, 15)
    assert alliance_discount.customer_segments == ["alianca-francesa"]
    assert alliance_discount.fulfillment_types == []


def test_setup_commercial_groups_repairs_legacy_row_without_losing_metadata(db):
    PriceTier.objects.create(
        ref="staff",
        name="Funcionarios",
        metadata={"custom": "keep", "discount_kind": "time"},
    )

    call_command("setup_commercial_groups", verbosity=0)

    tier = PriceTier.objects.get(ref="staff")
    assert tier.name == "Equipe"
    assert tier.metadata["custom"] == "keep"
    assert tier.metadata["discount_kind"] == "time"
    assert tier.metadata["rounding"] == 50
    assert Promotion.objects.filter(ref="grupo-staff", value=30, is_active=True).exists()


def test_setup_commercial_groups_never_reverts_operator_edits(db):
    call_command("setup_commercial_groups", verbosity=0)
    tier = PriceTier.objects.get(ref="staff")
    tier.name = "Time da casa"
    tier.metadata = {"discount_kind": "beneficio-manual", "rounding": 0}
    tier.save()
    promo = Promotion.objects.get(ref="grupo-staff")
    promo.value = 12
    promo.is_active = False
    promo.save()

    call_command("setup_commercial_groups", verbosity=0)

    tier.refresh_from_db()
    promo.refresh_from_db()
    assert tier.name == "Time da casa"
    assert tier.metadata == {"discount_kind": "beneficio-manual", "rounding": 0}
    assert (promo.value, promo.is_active) == (12, False)


def test_setup_commercial_groups_does_not_grant_discount_to_unknown_legacy_group(db):
    PriceTier.objects.create(ref="staff", name="Convênio antigo", metadata={"owner": "manual"})

    call_command("setup_commercial_groups", verbosity=0)

    tier = PriceTier.objects.get(ref="staff")
    assert tier.name == "Convênio antigo"
    assert tier.metadata == {"owner": "manual"}
    assert not Promotion.objects.filter(ref="grupo-staff").exists()
