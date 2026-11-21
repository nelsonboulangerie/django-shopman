"""O ``id_mch`` gravado vira ``ride_ref`` (M1b-a, #2552), e a volta desfaz.

O nome da TaOn só vive na porta dela; dentro da casa o identificador da corrida é
``ride_ref``, no bloco, em cada tentativa arquivada e no ``payload`` dos eventos.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps as django_apps
from shopman.orderman.models import Order, OrderEvent

pytestmark = [pytest.mark.django_db]

migration = importlib.import_module("shopman.shop.migrations.0129_courier_ride_ref")


def _order(ref, courier):
    return Order.objects.create(ref=ref, channel_ref="web", session_key=f"S-{ref}", status=Order.Status.READY,
                                snapshot={"items": []}, data={"fulfillment_type": "delivery", "courier": courier},
                                total_q=1000)


def test_forwards_renames_block_attempts_and_events_and_backwards_undoes():
    taon = _order("M-A", {"provider": "machine", "id_mch": "184532", "status": "E",
                          "attempts": [{"id_mch": "184000", "status": "C"}, "lixo"]})
    house = _order("M-B", {"provider": "own_fleet", "id_mch": "CASA-1", "status": "A"})
    untouched = _order("M-C", {"provider": "machine", "status": "D"})
    event = taon.emit_event(event_type="courier_status", actor="courier:webhook", payload={"status": "E", "id_mch": "184532"})
    other = taon.emit_event(event_type="note", actor="operator:ana", payload={"text": "oi"})

    migration.forwards(django_apps, None)
    taon.refresh_from_db()
    house.refresh_from_db()
    untouched.refresh_from_db()
    assert taon.data["courier"]["ride_ref"] == "184532" and "id_mch" not in taon.data["courier"]
    assert taon.data["courier"]["attempts"] == [{"ride_ref": "184000", "status": "C"}, "lixo"]
    assert house.data["courier"] == {"provider": "own_fleet", "ride_ref": "CASA-1", "status": "A"}
    assert untouched.data["courier"] == {"provider": "machine", "status": "D"}
    assert OrderEvent.objects.get(pk=event.pk).payload == {"status": "E", "ride_ref": "184532"}
    assert OrderEvent.objects.get(pk=other.pk).payload == {"text": "oi"}

    migration.backwards(django_apps, None)
    taon.refresh_from_db()
    assert taon.data["courier"]["id_mch"] == "184532"
    assert taon.data["courier"]["attempts"][0] == {"id_mch": "184000", "status": "C"}
    assert OrderEvent.objects.get(pk=event.pk).payload == {"status": "E", "id_mch": "184532"}
