"""O resolvedor único do serviço de entrega (DEV-2026-030, frente M1).

A M1 não muda comportamento: a corrida da TaOn resolve o mesmo módulo de antes. O que ela
acrescenta é o contrato (capacidades e estado da casa) e o serviço gravado na corrida.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings

from shopman.shop.adapters import courier_machine, courier_mock
from shopman.shop.models import DeliveryService
from shopman.shop.protocols import DeliveryCapabilities, RideState
from shopman.shop.services import delivery_services

pytestmark = pytest.mark.django_db

MOCK = "shopman.shop.adapters.courier_mock"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK)
def test_without_block_it_is_the_configured_central_as_before():
    assert delivery_services.courier_backend() is courier_mock


@override_settings(SHOPMAN_COURIER_ADAPTER=None)
def test_without_configuration_there_is_no_central():
    assert delivery_services.courier_backend() is None


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK)
def test_ride_of_the_taon_resolves_the_central():
    assert delivery_services.courier_backend({"service": "taon"}) is courier_mock


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK)
def test_ride_opened_before_the_m1_has_no_service_and_still_works():
    assert delivery_services.courier_backend({"ride_ref": "1", "status": "E"}) is courier_mock
    assert delivery_services.courier_backend({"service": "nao-existe"}) is courier_mock


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK)
def test_ride_of_the_house_resolves_the_house_module():
    from shopman.shop.adapters import courier_own_fleet

    assert delivery_services.courier_backend({"service": "casa"}) is courier_own_fleet


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK)
def test_capabilities_come_from_the_service():
    caps = delivery_services.capabilities({"service": "taon"})
    assert isinstance(caps, DeliveryCapabilities)
    assert caps.quote and caps.customer_tracking and not caps.assign
    assert delivery_services.capabilities({"service": "casa"}).assign


@pytest.mark.parametrize(
    ("letter", "state"),
    [
        ("D", RideState.SEARCHING), ("G", RideState.SEARCHING), ("P", RideState.SEARCHING),
        ("U", RideState.GROUPED), ("T", RideState.REASSIGNING), ("A", RideState.ASSIGNED),
        ("S", RideState.ASSIGNED), ("E", RideState.ON_ROUTE), ("F", RideState.DONE),
        ("N", RideState.NOT_SERVED), ("C", RideState.CANCELLED),
    ],
)
def test_every_taon_letter_has_a_house_state(letter, state):
    assert courier_machine.ride_state(letter) is state


def test_unknown_letter_has_no_state():
    assert courier_machine.ride_state("Z") is None
    assert courier_machine.ride_state("") is None


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK)
def test_ride_state_reads_the_block():
    assert delivery_services.ride_state({"service": "taon", "status": "E"}) is RideState.ON_ROUTE
    assert delivery_services.ride_state({"status": "a"}) is RideState.ASSIGNED
    assert delivery_services.ride_state({}) is None


@override_settings(SHOPMAN_COURIER_ADAPTER="shopman.shop.adapters.courier_machine")
def test_state_since_reads_the_hour_of_the_house_state_not_the_letter():
    """M1b-b (#2552): quem lê a hora pergunta pelo estado; "A" e "S" valem pela primeira."""
    block = {"service": "taon", "status": "E", "status_at": {
        "S": "2026-11-21T12:05:00-03:00", "A": "2026-11-21T12:02:00-03:00", "E": "2026-11-21T12:20:00-03:00"}}
    assert delivery_services.state_since(block, RideState.ASSIGNED) == "2026-11-21T12:02:00-03:00"
    assert delivery_services.state_since(block, RideState.ON_ROUTE) == "2026-11-21T12:20:00-03:00"
    assert delivery_services.state_since(block, RideState.DONE) is None
    assert delivery_services.state_since({}, RideState.ASSIGNED) is None


def test_new_ride_takes_the_default_service():
    assert delivery_services.new_ride_service_ref() == "taon"
    DeliveryService.objects.update(is_default=False)
    assert delivery_services.new_ride_service_ref() == ""


def test_the_house_cannot_be_the_default_because_auto_dispatch_needs_a_central():
    casa = DeliveryService.objects.get(ref="casa")
    DeliveryService.objects.filter(ref="taon").update(is_default=False)
    casa.is_default = True
    with pytest.raises(ValidationError) as err:
        casa.full_clean()
    assert "despacho automático" in str(err.value)
