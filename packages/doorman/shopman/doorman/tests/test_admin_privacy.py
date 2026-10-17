from __future__ import annotations

import pytest
from django.apps import apps

if not apps.is_installed("django.contrib.admin"):
    pytest.skip("Admin detail policy requires the host Admin runtime", allow_module_level=True)

from shopman.doorman.admin import VerificationCodeAdmin as DjangoVerificationCodeAdmin
from shopman.doorman.contrib.admin_unfold.admin import (
    VerificationCodeAdmin as UnfoldVerificationCodeAdmin,
)
from shopman.doorman.models import VerificationCode


@pytest.mark.parametrize(
    "admin_class",
    (DjangoVerificationCodeAdmin, UnfoldVerificationCodeAdmin),
)
def test_verification_code_detail_exposes_only_masked_target_and_hash_hint(admin_class):
    first_fieldset = admin_class.fieldsets[0][1]["fields"]
    assert first_fieldset == ["id", "code_hash_short", "target_masked"]
    assert "target_value" not in admin_class.readonly_fields
    assert "code_hash" not in admin_class.readonly_fields
    assert admin_class.search_fields == ["customer_id"]

    code = VerificationCode(
        target_value="secret.person@example.test",
        code_hash="a" * 64,
    )
    model_admin = object.__new__(admin_class)
    assert "secret.person" not in model_admin.target_masked(code)
    assert model_admin.code_hash_short(code) != code.code_hash
