import pytest

from shopman.storefront.intents._phone import normalize_phone_input

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("value", ["(43) 9840-4900", "+554398404900", "9840-4900"])
def test_customer_phone_input_requires_missing_digit_to_be_corrected(value):
    assert normalize_phone_input(value) == ""


def test_gift_does_not_save_an_invented_recipient():
    from shopman.storefront.intents.gift import build_gift_data

    data, errors = build_gift_data(is_gift=True, fulfillment_type="delivery",
                                   recipient_name="Maria", recipient_phone="(43) 9840-4900")
    assert data is None
    assert "recipient_phone" in errors
