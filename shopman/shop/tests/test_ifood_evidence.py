"""Evidence reads are bounded and bearer credentials never follow untrusted URLs."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests

from shopman.shop.services import ifood_evidence as evidence

URL = "https://merchant-api.ifood.com.br/order/v1.0/orders/order-1/cancellationEvidences/image-1"


def order_with(url=URL):
    return SimpleNamespace(channel_ref="ifood", external_ref="order-1", data={"ifood": {"handshakes": {
        "dispute-1": {"raw": {"metadata": {"evidences": [{"url": url}]}}},
    }}})


def response(*, mime="image/jpeg", status=200, chunks=(b"image bytes",), length=None):
    result = Mock(status_code=status, headers={"Content-Type": mime})
    if length is not None:
        result.headers["Content-Length"] = length
    result.iter_content.return_value = iter(chunks)
    manager = Mock()
    manager.__enter__ = Mock(return_value=result)
    manager.__exit__ = Mock(return_value=False)
    return manager


@pytest.mark.parametrize("mime", ["image/jpeg", "application/pdf", "image/png; charset=binary"])
def test_registered_evidence_uses_server_auth_and_binary_response(mime):
    with patch.object(evidence.ifood_auth, "authorized_headers", return_value={"Authorization": "Bearer test"}), patch.object(evidence.requests, "get", return_value=response(mime=mime)) as get:
        assert evidence.fetch_evidence(order_with(), dispute_id="dispute-1", index=0) == (b"image bytes", mime.split(";")[0])
    assert get.call_args.args == (URL,)
    assert get.call_args.kwargs["allow_redirects"] is False
    assert get.call_args.kwargs["stream"] is True
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer test"


@pytest.mark.parametrize("url", [
    "https://example.com/evidence", URL.replace("order-1", "other-order"),
    URL.replace("https:", "http:"), URL + "?url=https://example.com", URL + "#fragment",
    URL.replace("merchant-api.ifood.com.br", "merchant-api.ifood.com.br.evil.com"),
    URL.replace("merchant-api.ifood.com.br", "user@merchant-api.ifood.com.br"),
    URL.replace("merchant-api.ifood.com.br", "merchant-api.ifood.com.br:443"),
    URL + "/../secret", URL + "%2fsecret", "https://[", "\n" + URL,
])
def test_untrusted_registered_urls_never_obtain_credentials_or_fetch(url):
    with patch.object(evidence.ifood_auth, "authorized_headers") as auth, patch.object(evidence.requests, "get") as get, pytest.raises(evidence.EvidenceUnavailable):
        evidence.fetch_evidence(order_with(url), dispute_id="dispute-1", index=0)
    auth.assert_not_called()
    get.assert_not_called()


@pytest.mark.parametrize("dispute_id,index", [("missing", 0), ("dispute-1", -1), ("dispute-1", 1), ("dispute-1", True), ("dispute-1", "0")])
def test_evidence_must_exist_in_selected_dispute(dispute_id, index):
    with patch.object(evidence.requests, "get") as get, pytest.raises(evidence.EvidenceUnavailable):
        evidence.fetch_evidence(order_with(), dispute_id=dispute_id, index=index)
    get.assert_not_called()


@pytest.mark.parametrize("kwargs", [
    {"status": 302}, {"status": 403}, {"mime": "application/json"}, {"mime": "text/html"},
    {"mime": "image/svg+xml"}, {"length": str(evidence.MAX_BYTES + 1)},
    {"length": "invalid"}, {"chunks": ()},
])
def test_rejects_redirect_error_active_content_and_excess_size(kwargs):
    with patch.object(evidence.ifood_auth, "authorized_headers", return_value={"Authorization": "test"}), patch.object(evidence.requests, "get", return_value=response(**kwargs)), pytest.raises(evidence.EvidenceUnavailable):
        evidence.fetch_evidence(order_with(), dispute_id="dispute-1", index=0)


def test_chunked_body_enforces_limit_even_with_small_declared_length():
    with patch.object(evidence, "MAX_BYTES", 5), patch.object(evidence.ifood_auth, "authorized_headers", return_value={"Authorization": "test"}), patch.object(evidence.requests, "get", return_value=response(chunks=(b"123", b"456"), length="1")), pytest.raises(evidence.EvidenceUnavailable):
        evidence.fetch_evidence(order_with(), dispute_id="dispute-1", index=0)


def test_transport_failure_is_sanitized():
    with patch.object(evidence.ifood_auth, "authorized_headers", return_value={"Authorization": "test"}), patch.object(evidence.requests, "get", side_effect=requests.Timeout("secret request details")), pytest.raises(evidence.EvidenceUnavailable) as error:
        evidence.fetch_evidence(order_with(), dispute_id="dispute-1", index=0)
    assert "secret" not in str(error.value)


def test_links_keep_original_indices_and_do_not_fetch_external_urls():
    order = order_with()
    order.data["ifood"]["handshakes"]["dispute-1"]["raw"]["metadata"]["evidences"] = [
        {"url": "javascript:alert(1)"}, {"url": URL}, {"url": "https://example.com/image"},
        {"url": URL.replace("order-1", "other-order")}, {"url": "https://user:password@example.com/image"},
    ]
    with patch.object(evidence.requests, "get") as get:
        assert evidence.evidence_links(order, "dispute-1") == [
            {"url": URL, "index": 1, "protected": True},
            {"url": "https://example.com/image", "index": 2, "protected": False},
        ]
    get.assert_not_called()
