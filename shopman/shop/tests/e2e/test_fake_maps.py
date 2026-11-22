"""Os mapas falsos do harness respondem o geocoding que a loja faz, e cada endereço cai na faixa dele.

O ``geocoding`` de produção roda inteiro contra o fake (só o endereço da API muda, como o
``settings_e2e`` faz), e a distância é a haversine da loja do seed. Se uma faixa do seed
mudar, ou a loja mudar de lugar, isto reprova antes de a J15 medir a faixa errada.
"""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

import pytest
from django.core.cache import cache

from shopman.shop.services import geocoding
from shopman.shop.services.delivery_distance import haversine_km
from shopman.shop.tests.e2e.fake_maps import ADDRESSES, _handler

pytestmark = pytest.mark.django_db

# A loja do seed (`seed._seed_shop`) e as faixas (`seed._seed_delivery_distance_bands`).
SEED_SHOP = (-23.3348384, -51.1673157)
SEED_BANDS_KM = ((3.0, 500), (6.0, 800), (10.0, 1200))


def _band_fee(km: float) -> int | None:
    for limit, fee_q in SEED_BANDS_KM:
        if km <= limit:
            return fee_q
    return None


@pytest.fixture
def fake(settings, monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setattr(geocoding, "GEOCODE_URL", f"{base}/maps/api/geocode/json")
    settings.GOOGLE_MAPS_SERVER_API_KEY = "e2e-fake-maps-local-only"
    cache.clear()
    try:
        yield base
    finally:
        cache.clear()
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    ("text", "fee_q"),
    [
        ("Rua Pernambuco, 1000 - Centro, Londrina - PR, 86020-120", 500),
        ("Avenida Saul Elkind, 2000 - Lago Parque, Londrina - PR, 86082-000", 1200),
        ("Estrada do Limoeiro, 10 - Irerê, Londrina - PR, 86118-000", None),
    ],
)
def test_o_geocoding_de_producao_devolve_a_coordenada_da_faixa(fake, text, fee_q):
    result = geocoding.forward_geocode_structured(text)

    assert result is not None
    assert result.city == "Londrina"
    assert result.state_code == "PR"
    km = haversine_km(*SEED_SHOP, result.latitude, result.longitude)
    assert _band_fee(km) == fee_q


def test_a_distancia_anotada_na_tabela_e_a_medida(fake):
    for entry in ADDRESSES.values():
        assert round(haversine_km(*SEED_SHOP, entry["lat"], entry["lng"]), 1) == entry["km"]


def test_sem_cep_no_texto_acha_pela_rua(fake):
    # O texto que a loja monta do endereço digitado não traz o CEP.
    coords = geocoding.forward_geocode("Avenida Saul Elkind, 2000 - Lago Parque - Londrina/PR")

    assert coords is not None
    assert _band_fee(haversine_km(*SEED_SHOP, *coords)) == 1200


def test_endereco_fora_da_tabela_nao_tem_coordenada(fake):
    assert geocoding.forward_geocode("Rua Jorge Velho, 140 - Bela Suíça, Londrina - PR, 86050-480") is None


def test_o_reverso_acha_o_endereco_perto_da_coordenada(fake):
    result = geocoding.reverse_geocode(-23.3131, -51.1626)

    assert result.postal_code == "86020-120"
    assert result.route == "Rua Pernambuco"


def test_viacep_no_formato_do_viacep(fake):
    with urlopen(f"{fake}/ws/86118000/json/", timeout=5) as response:
        body = json.loads(response.read())
    assert body["logradouro"] == "Estrada do Limoeiro"
    assert body["localidade"] == "Londrina"
    assert body["uf"] == "PR"
    with urlopen(f"{fake}/ws/00000000/json/", timeout=5) as response:
        assert json.loads(response.read()) == {"erro": True}
