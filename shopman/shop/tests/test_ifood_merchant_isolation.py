"""Keep test-store event processing isolated from other authorized merchants."""

from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from shopman.shop.services import ifood_events


@override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store"})
def test_rejected_merchant_filter_never_retries_without_it():
    response = MagicMock(status_code=400, text="Invalid merchant filter")
    with (
        patch.object(ifood_events.ifood_auth, "authorized_headers", return_value={"Authorization": "Bearer test"}),
        patch.object(ifood_events.requests, "get", return_value=response) as get,
    ):
        assert ifood_events.poll() == []

    get.assert_called_once()
    assert get.call_args.kwargs["headers"]["x-polling-merchants"] == "test-store"


@pytest.mark.parametrize("code", ["PLACED", "CONFIRMED", "CANCELLED"])
@override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store"})
def test_other_merchant_is_neither_processed_nor_acknowledged(code):
    event = {"id": "foreign", "fullCode": code, "orderId": "o1", "merchantId": "production-store"}
    with (
        patch.object(ifood_events, "_process_placed") as process,
        patch.object(ifood_events, "acknowledge") as acknowledge,
    ):
        summary = ifood_events.process_events([event])

    assert summary["failed"] == 1
    assert summary["ingested"] == summary["ignored"] == 0
    process.assert_not_called()
    acknowledge.assert_not_called()


@override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store"})
def test_mixed_batch_only_processes_and_acknowledges_matching_or_legacy_events():
    events = [
        {"id": "foreign", "code": "PLC", "orderId": "o1", "merchantId": "production-store"},
        {"id": "matching", "code": "PLC", "orderId": "o2", "merchantId": "test-store"},
        {"id": "legacy", "code": "PLC", "orderId": "o3"},
    ]
    with (
        patch.object(ifood_events, "_process_placed", return_value="ingested") as process,
        patch.object(ifood_events, "acknowledge", return_value=True) as acknowledge,
    ):
        summary = ifood_events.process_events(events)

    assert summary["ingested"] == 2
    assert summary["failed"] == 1
    assert [call.args for call in process.call_args_list] == [("matching", "o2"), ("legacy", "o3")]
    acknowledge.assert_called_once_with(["matching", "legacy"])


@override_settings(SHOPMAN_IFOOD={})
def test_unconfigured_merchant_preserves_existing_multi_merchant_mode():
    event = {"id": "e1", "code": "PLC", "orderId": "o1", "merchantId": "store"}
    with (
        patch.object(ifood_events, "_process_placed", return_value="ingested"),
        patch.object(ifood_events, "acknowledge", return_value=True) as acknowledge,
    ):
        assert ifood_events.process_events([event])["ingested"] == 1
    acknowledge.assert_called_once_with(["e1"])
