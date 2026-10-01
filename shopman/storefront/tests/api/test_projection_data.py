"""``projection_data``: o card repetido no cardápio sai igual, convertido uma vez."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from shopman.shop.projections.types import Availability
from shopman.storefront.api.projections import projection_data


class _Tone(Enum):
    INFO = "info"


@dataclass(frozen=True)
class _Card:
    sku: str
    availability: Availability
    price: Decimal
    tags: tuple[str, ...] = ()
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class _Section:
    label: str
    items: tuple[_Card, ...]


@dataclass(frozen=True)
class _Menu:
    items: tuple[_Card, ...]
    sections: tuple[_Section, ...]
    featured: tuple[_Card, ...]
    tone: _Tone


def test_repeated_card_is_converted_once_and_serializes_identically():
    card = _Card(
        sku="PAO",
        availability=Availability.LOW_STOCK,
        price=Decimal("1.50"),
        tags=("trigo",),
        meta={"cor": ["#fff"], 3: None},
    )
    other = _Card(sku="CAFE", availability=Availability.AVAILABLE, price=Decimal("5"))
    menu = _Menu(
        items=(card, other),
        sections=(_Section("Pães", (card,)), _Section("Destaques", (other, card))),
        featured=(card,),
        tone=_Tone.INFO,
    )

    data = projection_data(menu)

    # Mesmo objeto de entrada, mesmo dict de saída: convertido uma vez só.
    assert data["items"][0] is data["sections"][0]["items"][0] is data["featured"][0]
    assert json.dumps(data, sort_keys=True) == json.dumps(
        {
            "items": [
                {"sku": "PAO", "availability": "low_stock", "price": "1.50", "tags": ["trigo"],
                 "meta": {"cor": ["#fff"], "3": None}},
                {"sku": "CAFE", "availability": "available", "price": "5", "tags": [], "meta": {}},
            ],
            "sections": [
                {"label": "Pães", "items": [
                    {"sku": "PAO", "availability": "low_stock", "price": "1.50", "tags": ["trigo"],
                     "meta": {"cor": ["#fff"], "3": None}},
                ]},
                {"label": "Destaques", "items": [
                    {"sku": "CAFE", "availability": "available", "price": "5", "tags": [], "meta": {}},
                    {"sku": "PAO", "availability": "low_stock", "price": "1.50", "tags": ["trigo"],
                     "meta": {"cor": ["#fff"], "3": None}},
                ]},
            ],
            "featured": [
                {"sku": "PAO", "availability": "low_stock", "price": "1.50", "tags": ["trigo"],
                 "meta": {"cor": ["#fff"], "3": None}},
            ],
            "tone": "info",
        },
        sort_keys=True,
    )


def test_str_enum_becomes_its_value_not_the_member():
    """``Availability`` herda de ``str``: o caminho rápido não pode deixá-lo passar cru."""
    converted = projection_data({"a": Availability.UNAVAILABLE})["a"]
    assert type(converted) is str
    assert converted == "unavailable"


def test_each_call_starts_a_fresh_memo():
    card = _Card(sku="PAO", availability=Availability.AVAILABLE, price=Decimal("1"))
    assert projection_data(card) is not projection_data(card)
