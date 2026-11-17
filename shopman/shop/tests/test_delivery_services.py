"""Cadastro de quem leva a entrega (DEV-2026-030, frente M0).

Decisões do dono que estes testes travam (16/11/2026):
- o serviço padrão é configurável no Admin e hoje é a TaOn; os entregadores da casa são opção;
- o valor do entregador da casa sai de uma tabela da casa por distância, mais parada a mais e
  volta, com exceção por entregador.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from shopman.shop.models import Courier, CourierRate, DeliveryService
from shopman.shop.services.delivery_rates import ride_value

pytestmark = pytest.mark.django_db


@pytest.fixture
def taon():
    return DeliveryService.objects.get(ref="taon")


@pytest.fixture
def casa():
    return DeliveryService.objects.get(ref="casa")


@pytest.fixture
def diego(casa):
    return Courier.objects.create(service=casa, ref="diego", name="Diego", phone="+5543999990000")


@pytest.fixture
def house_table(casa):
    CourierRate.objects.create(service=casa, max_km=Decimal("3"), value_q=800, extra_stop_q=300, return_q=200)
    CourierRate.objects.create(service=casa, max_km=Decimal("6"), value_q=1200, extra_stop_q=300, return_q=200)
    CourierRate.objects.create(service=casa, max_km=Decimal("10"), value_q=1600, extra_stop_q=300, return_q=200)


# ── os dois serviços de hoje nascem com a migração ───────────────────────────


def test_migration_creates_taon_as_default_and_the_house_as_option(taon, casa):
    assert taon.kind == DeliveryService.KIND_MACHINE
    assert taon.is_default and taon.is_active
    assert casa.kind == DeliveryService.KIND_OWN_FLEET
    assert not casa.is_default
    assert DeliveryService.default() == taon


def test_only_one_default_in_the_database(taon, casa):
    casa.is_default = True
    with pytest.raises(IntegrityError), transaction.atomic():
        casa.save()


def test_admin_validation_names_the_current_default(taon, casa):
    casa.is_default = True
    with pytest.raises(ValidationError) as err:
        casa.full_clean()
    assert "O padrão hoje é TaOn" in str(err.value)


def test_default_must_be_active(taon):
    taon.is_active = False
    with pytest.raises(ValidationError):
        taon.full_clean()


def test_switching_the_default_moves_it(taon, casa):
    taon.is_default = False
    taon.save()
    casa.is_default = True
    casa.full_clean()
    casa.save()
    assert DeliveryService.default() == casa


# ── entregador ──────────────────────────────────────────────────────────────


def test_courier_phone_is_normalized(casa):
    courier = Courier(service=casa, ref="rui", name="Rui", phone="(43) 99999-1234")
    courier.full_clean()
    assert courier.phone == "+5543999991234"


def test_courier_phone_must_be_valid(casa):
    courier = Courier(service=casa, ref="rui", name="Rui", phone="123")
    with pytest.raises(ValidationError) as err:
        courier.full_clean()
    assert "phone" in err.value.message_dict


def test_courier_belongs_to_the_house_service_only(taon):
    courier = Courier(service=taon, ref="leo", name="Léo", phone="+5543999990001")
    with pytest.raises(ValidationError) as err:
        courier.full_clean()
    assert "service" in err.value.message_dict


def test_rate_of_a_courier_from_another_service_is_refused(casa, diego):
    other = DeliveryService.objects.create(ref="casa-2", name="Outra equipe", kind=DeliveryService.KIND_OWN_FLEET)
    rate = CourierRate(service=other, courier=diego, value_q=1000)
    with pytest.raises(ValidationError) as err:
        rate.full_clean()
    assert "courier" in err.value.message_dict


def test_duplicate_distance_for_the_same_courier_is_refused(casa, house_table):
    rate = CourierRate(service=casa, max_km=Decimal("6"), value_q=999)
    with pytest.raises(ValidationError) as err:
        rate.full_clean()
    assert "max_km" in err.value.message_dict


# ── a régua do valor da corrida ─────────────────────────────────────────────


def test_house_table_picks_the_smallest_band_that_reaches(casa, house_table):
    assert ride_value(casa, km=2.5).value_q == 800
    assert ride_value(casa, km=3).value_q == 800  # limite inclusivo
    assert ride_value(casa, km=3.01).value_q == 1200
    assert ride_value(casa, km=7.4).source == "house"


def test_extra_stops_and_return_are_added(casa, house_table):
    # 7,4 km com 2 paradas e volta: R$ 16,00 + R$ 3,00 + R$ 2,00
    assert ride_value(casa, km=7.4, stops=2, with_return=True).value_q == 2100


def test_beyond_the_table_without_an_any_distance_line_has_no_value(casa, house_table):
    assert ride_value(casa, km=12) is None


def test_any_distance_line_covers_what_the_bands_do_not(casa, house_table):
    CourierRate.objects.create(service=casa, max_km=None, value_q=2500)
    assert ride_value(casa, km=12).value_q == 2500
    assert ride_value(casa, km=2).value_q == 800


def test_courier_agreement_replaces_the_house_table_for_him_only(casa, house_table, diego):
    CourierRate.objects.create(service=casa, courier=diego, max_km=None, value_q=1000)
    mine = ride_value(casa, km=7.4, stops=2, with_return=True, courier=diego)
    assert (mine.value_q, mine.source) == (1000, "courier")
    rui = Courier.objects.create(service=casa, ref="rui", name="Rui", phone="+5543999991234")
    assert ride_value(casa, km=7.4, courier=rui).value_q == 1600


def test_api_service_has_no_table(taon):
    assert ride_value(taon, km=3) is None


def test_a_ride_has_at_least_one_stop(casa, house_table):
    with pytest.raises(ValueError):
        ride_value(casa, km=3, stops=0)


# ── Admin ───────────────────────────────────────────────────────────────────


@pytest.fixture
def admin_client(client):
    from django.contrib.auth.models import User

    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")
    client.force_login(User.objects.create_superuser("entregas-admin", "entregas@test.com", "pw"))
    return client


def test_admin_screens_render_with_rows(admin_client, casa, diego, house_table):
    from django.urls import reverse

    rate = CourierRate.objects.filter(courier__isnull=True).first()
    for name, pk in (("deliveryservice", casa.pk), ("courier", diego.pk), ("courierrate", rate.pk)):
        assert admin_client.get(reverse(f"admin:shop_{name}_changelist")).status_code == 200
        assert admin_client.get(reverse(f"admin:shop_{name}_change", args=[pk])).status_code == 200
    assert admin_client.get(reverse("admin:shop_courier_add")).status_code == 200


def test_agreed_value_saved_from_the_courier_form_inherits_his_service(admin_client, casa):
    from django.urls import reverse

    response = admin_client.post(
        reverse("admin:shop_courier_add"),
        {
            "service": casa.pk,
            "name": "Ana",
            "ref": "ana",
            "phone": "(43) 98888-7777",
            "vehicle": "Moto vermelha",
            "is_active": "on",
            "rates-TOTAL_FORMS": "1",
            "rates-INITIAL_FORMS": "0",
            "rates-MIN_NUM_FORMS": "0",
            "rates-MAX_NUM_FORMS": "1000",
            "rates-0-max_km": "",
            "rates-0-value_q": "1000",
            "rates-0-extra_stop_q": "0",
            "rates-0-return_q": "0",
        },
    )
    assert response.status_code == 302, response.content.decode()[:500]
    ana = Courier.objects.get(ref="ana")
    assert ana.phone == "+5543988887777"
    rate = ana.rates.get()
    assert rate.service_id == casa.pk
    assert ride_value(casa, km=9, courier=ana).value_q == 1000
