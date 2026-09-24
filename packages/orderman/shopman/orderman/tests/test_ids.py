import re
from datetime import date

import pytest
from shopman.orderman.contrib.refs.types import ORDER_REF
from shopman.orderman.ids import generate_order_ref
from shopman.refs.registry import get_ref_type, register_ref_type

# generate_order_ref sorteia e checa colisão no banco (retry) → precisa de DB.
pytestmark = pytest.mark.django_db


def test_generate_order_ref_uses_yymmdd_business_date():
    if get_ref_type("ORDER_REF") is None:
        register_ref_type(ORDER_REF)

    ref = generate_order_ref(channel_ref="pdv", business_date=date(2026, 5, 4))

    assert re.fullmatch(r"PDV-260504-[A-Z]\d{2}", ref)


def test_generate_order_ref_accepts_real_channel_refs():
    if get_ref_type("ORDER_REF") is None:
        register_ref_type(ORDER_REF)

    ref = generate_order_ref(channel_ref="delivery", business_date=date(2026, 5, 4))

    assert re.fullmatch(r"DELIVERY-260504-[A-Z]\d{2}", ref)


def test_generate_order_ref_fallback_keeps_channel_and_yymmdd(monkeypatch):
    def unavailable(*args, **kwargs):
        raise LookupError

    monkeypatch.setattr("shopman.refs.generators.generate_value", unavailable)
    ref = generate_order_ref(channel_ref="web", business_date=date(2026, 5, 4))

    assert re.fullmatch(r"WEB-260504-[A-Z]\d{2}", ref)


def test_generate_order_ref_retries_past_collision(monkeypatch):
    # Aleatório pode repetir: se o candidato já existe, sorteia de novo até um livre.
    from shopman.orderman.models import Order

    if get_ref_type("ORDER_REF") is None:
        register_ref_type(ORDER_REF)
    Order.objects.create(ref="WEB-260504-A17", channel_ref="WEB", session_key="k1", total_q=0)

    seq = iter(["WEB-260504-A17", "WEB-260504-B22"])  # 1º colide, 2º livre
    monkeypatch.setattr("shopman.orderman.ids._order_ref_candidate", lambda ch, day: next(seq))

    ref = generate_order_ref(channel_ref="web", business_date=date(2026, 5, 4))
    assert ref == "WEB-260504-B22"


# ── Sufixo do canal ────────────────────────────────────────────────────────────
# O marketplace já batizou o pedido, e é esse número que o cliente, o portal e o
# suporte falam. Adotá-lo evita a tradução de cabeça que o operador fazia.


def test_preferred_suffix_becomes_the_ref_when_free():
    ref = generate_order_ref(channel_ref="ifood", business_date=date(2026, 9, 19), preferred_suffix="4994")

    assert ref == "IFOOD-260919-4994"


def test_preferred_suffix_falls_back_to_random_when_taken():
    from shopman.orderman.models import Order

    Order.objects.create(ref="IFOOD-260919-4994", channel_ref="ifood", status=Order.Status.NEW)

    ref = generate_order_ref(channel_ref="ifood", business_date=date(2026, 9, 19), preferred_suffix="4994")

    assert ref != "IFOOD-260919-4994"
    assert re.fullmatch(r"IFOOD-260919-[A-Z]\d{2}", ref)


@pytest.mark.parametrize("suffix", ["", "   ", "X", "4994/../etc", "a b", "TOOLONGSUFFIX", "49 94"])
def test_unusable_preferred_suffix_falls_back_to_random(suffix):
    """O ref é lido em voz alta, digitado na busca e impresso: só entra o que serve."""
    ref = generate_order_ref(channel_ref="ifood", business_date=date(2026, 9, 19), preferred_suffix=suffix)

    assert re.fullmatch(r"IFOOD-260919-[A-Z]\d{2}", ref)


def test_preferred_suffix_is_uppercased():
    ref = generate_order_ref(channel_ref="ifood", business_date=date(2026, 9, 19), preferred_suffix="ab12")

    assert ref == "IFOOD-260919-AB12"


def test_house_channels_keep_the_random_suffix_untouched():
    """A exceção é do marketplace. Quem chama sem o argumento não muda em nada."""
    for channel in ("pdv", "web", "delivery"):
        ref = generate_order_ref(channel_ref=channel, business_date=date(2026, 9, 19))
        assert re.fullmatch(rf"{channel.upper()}-260919-[A-Z]\d{{2}}", ref)
