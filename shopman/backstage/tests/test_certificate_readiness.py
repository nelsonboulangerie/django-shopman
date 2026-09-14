import base64

import pytest
from django.test import override_settings

from shopman.backstage.services.certificate_readiness import certificate_issue
from shopman.backstage.services.integration_readiness import efi_pix_readiness, purchase_nfe_readiness
from shopman.backstage.tests.certificate_fixtures import synthetic_certificate


@pytest.mark.parametrize("pfx", [False, True])
@pytest.mark.parametrize("start,end,issue", [(-1, 1, ""), (-2, -1, "expired"), (1, 2, "not_yet_valid")])
def test_certificate_validity(tmp_path, pfx, start, end, issue):
    path = tmp_path / "certificate"
    path.write_bytes(synthetic_certificate(pfx=pfx, start=start, end=end))
    assert certificate_issue(path=str(path), pfx=pfx) == issue


def test_invalid_file_and_password_are_sanitized(tmp_path):
    path = tmp_path / "certificate"
    assert certificate_issue(path=str(path)) == "invalid"
    path.write_text("sensitive-invalid-data")
    assert certificate_issue(path=str(path)) == "invalid"
    data = base64.b64encode(synthetic_certificate(pfx=True, password=b"test-secret")).decode()
    assert certificate_issue(pfx_base64=data, pfx=True, password="wrong") == "invalid"
    assert certificate_issue(pfx_base64=data, pfx=True, password="test-secret") == ""


def test_expired_certificates_make_readiness_unsafe(tmp_path):
    path = tmp_path / "efi.pem"
    path.write_bytes(synthetic_certificate(start=-2, end=-1))
    with override_settings(SHOPMAN_EFI={"certificate_path": str(path)}):
        readiness = efi_pix_readiness()
    assert readiness.status == "error"
    assert "EFI_CERTIFICATE_expired" in readiness.missing
    data = base64.b64encode(synthetic_certificate(pfx=True, start=-2, end=-1)).decode()
    with override_settings(SHOPMAN_PURCHASE_NFE={"certificate_pfx_base64": data}):
        readiness = purchase_nfe_readiness()
    assert readiness.status == "error"
    assert "PURCHASE_NFE_CERTIFICATE_expired" in readiness.missing
