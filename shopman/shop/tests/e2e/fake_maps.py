"""Mapas falsos, locais, para as jornadas da loja (#2569, item 4).

A taxa da entrega é por DISTÂNCIA (``DeliveryFeeModifier`` → ``DeliveryDistanceBand``),
e a distância sai de duas coisas: a coordenada da loja (``Shop.latitude/longitude``, do
seed) e a do endereço. No caminho que a cliente percorre sem a chave de navegador do
Google (o manual do ``AddressPicker``: CEP, rua, número), o endereço chega SEM
coordenada, e o servidor o geocodifica pelo TEXTO (``geocoding.forward_geocode``, a API
de Geocoding do Google, com a chave de servidor). Sem chave na pilha, não havia
coordenada, não havia distância, e a loja caía na taxa-padrão: a faixa nunca era medida.

A distância em si NÃO é chamada externa: é haversine local
(``delivery_distance.haversine_km``) entre as duas coordenadas. Não há API de rotas
para imitar. O que precisa de um lado de lá é o geocoding, e é isto aqui, que responde
o pedaço do contrato que a loja usa, a partir de uma tabela FIXA:

* ``GET /maps/api/geocode/json?address=…&key=…``: a geocodificação direta. Acha o
  endereço da tabela pelo CEP que vem no texto ou, sem CEP (o texto que a loja monta
  é "Rua X, 140 - Bairro - Cidade/UF"), pela rua; fora da tabela, ``ZERO_RESULTS``
  (a loja segue como sem a chave: taxa-padrão na cidade da loja).
* ``GET /maps/api/geocode/json?latlng=…&key=…``: o reverso (botão "usar minha
  localização" e a conferência antifraude), pelo endereço da tabela a menos de 1 km.
* ``GET /ws/<cep>/json/``: o ViaCEP, no formato dele, para a jornada desviar a
  consulta que o NAVEGADOR faz ao digitar o CEP (``AddressPicker.lookupCep``): a URL é
  fixa no componente, então quem desvia é a jornada (``page.route``), para este mesmo
  servidor. CEP fora da tabela devolve ``{"erro": true}``, como o ViaCEP.

Sem ``key``, o geocoding responde ``REQUEST_DENIED``, como o Google. Qualquer outra rota
responde 404 e fica no log.

A tabela: endereços de Londrina com coordenadas ESCOLHIDAS para cair numa faixa do seed
(``seed._seed_delivery_distance_bands``: até 3 km R$ 5,00, até 6 km R$ 8,00, até 10 km
R$ 12,00, além disso fora da área), medidas da loja do seed (-23,3348384, -51,1673157).
Não são as coordenadas reais desses CEPs; são as que fazem cada faixa ser medida. Fora o
da J8, nenhum está em zona de exceção (bairro Bela Suíça, CEP 862…), para que a
distância decida.

Uso (o ``scripts/run_storefront_journeys.sh`` sobe sozinho)::

    python -m shopman.shop.tests.e2e.fake_maps --port 12192
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

#: CEP (só dígitos) → endereço. ``km`` é a distância haversine da loja do seed, para
#: quem lê saber em que faixa cada um cai (o teste do fake confere).
ADDRESSES: dict[str, dict] = {
    # O endereço da J8 (#3282): o bairro da loja, zona de cortesia do seed (a zona decide
    # a taxa antes da distância). Está aqui para o ViaCEP da J8 não sair da máquina.
    "86050480": {
        "route": "Rua Jorge Velho",
        "neighborhood": "Bela Suíça",
        "lat": -23.3385,
        "lng": -51.1700,
        "km": 0.5,
    },
    # Até 3 km: R$ 5,00.
    "86020120": {
        "route": "Rua Pernambuco",
        "neighborhood": "Centro",
        "lat": -23.3130,
        "lng": -51.1625,
        "km": 2.5,
    },
    # De 6 a 10 km: R$ 12,00.
    "86082000": {
        "route": "Avenida Saul Elkind",
        "neighborhood": "Lago Parque",
        "lat": -23.2700,
        "lng": -51.1650,
        "km": 7.2,
    },
    # Além de 10 km: fora da área (a recusa, com a troca por retirada).
    "86118000": {
        "route": "Estrada do Limoeiro",
        "neighborhood": "Irerê",
        "lat": -23.4600,
        "lng": -51.1170,
        "km": 14.8,
    },
}
CITY, STATE, STATE_NAME = "Londrina", "PR", "Paraná"

_CEP = re.compile(r"(?<!\d)(\d{5})-?(\d{3})(?!\d)")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_km * math.asin(min(1.0, math.sqrt(a)))


def _masked(cep: str) -> str:
    return f"{cep[:5]}-{cep[5:]}"


def _street_number(address: str) -> str:
    """O número que a cliente digitou ("Rua X, 140 - …"), para devolver no resultado."""
    match = re.search(r",\s*(\d+[A-Za-z]?)\b", address)
    return match.group(1) if match else ""


def geocode_result(cep: str, street_number: str = "") -> dict:
    """Um resultado no formato da API de Geocoding do Google."""
    entry = ADDRESSES[cep]
    components = [
        {"long_name": entry["route"], "short_name": entry["route"], "types": ["route"]},
        {"long_name": entry["neighborhood"], "short_name": entry["neighborhood"], "types": ["sublocality_level_1", "sublocality", "political"]},
        {"long_name": CITY, "short_name": CITY, "types": ["administrative_area_level_2", "political"]},
        {"long_name": STATE_NAME, "short_name": STATE, "types": ["administrative_area_level_1", "political"]},
        {"long_name": "Brasil", "short_name": "BR", "types": ["country", "political"]},
        {"long_name": _masked(cep), "short_name": _masked(cep), "types": ["postal_code"]},
    ]
    if street_number:
        components.insert(0, {"long_name": street_number, "short_name": street_number, "types": ["street_number"]})
    number = f", {street_number}" if street_number else ""
    return {
        "address_components": components,
        "formatted_address": f"{entry['route']}{number} - {entry['neighborhood']}, {CITY} - {STATE}, {_masked(cep)}, Brasil",
        "geometry": {"location": {"lat": entry["lat"], "lng": entry["lng"]}, "location_type": "ROOFTOP"},
        "place_id": f"fake-maps-{cep}",
        "types": ["street_address"],
    }


def _plain(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(folded.lower().split())


def forward(address: str) -> dict:
    found = ""
    for match in _CEP.finditer(address or ""):
        cep = "".join(match.groups())
        if cep in ADDRESSES:
            found = cep
            break
    if not found:
        plain = _plain(address)
        found = next((cep for cep, entry in ADDRESSES.items() if _plain(entry["route"]) in plain), "")
    if not found:
        return {"status": "ZERO_RESULTS", "results": []}
    return {"status": "OK", "results": [geocode_result(found, _street_number(address))]}


def reverse(latlng: str) -> dict:
    try:
        lat, lng = (float(part) for part in latlng.split(","))
    except ValueError:
        return {"status": "INVALID_REQUEST", "results": []}
    near = [(cep, _haversine_km(lat, lng, entry["lat"], entry["lng"])) for cep, entry in ADDRESSES.items()]
    near = [(cep, km) for cep, km in near if km <= 1.0]
    if not near:
        return {"status": "ZERO_RESULTS", "results": []}
    cep = min(near, key=lambda item: item[1])[0]
    return {"status": "OK", "results": [geocode_result(cep)]}


def viacep(cep: str) -> dict:
    """O formato do ViaCEP (https://viacep.com.br/ws/<cep>/json/)."""
    entry = ADDRESSES.get(cep)
    if entry is None:
        return {"erro": True}
    return {
        "cep": _masked(cep),
        "logradouro": entry["route"],
        "complemento": "",
        "unidade": "",
        "bairro": entry["neighborhood"],
        "localidade": CITY,
        "uf": STATE,
        "estado": STATE_NAME,
        "regiao": "Sul",
        "ibge": "4113700",
        "gia": "",
        "ddd": "43",
        "siafi": "7563",
    }


def _handler():
    class Handler(BaseHTTPRequestHandler):
        server_version = "FakeMaps/1"

        def log_request(self, code="-", size="-"):  # assinatura da stdlib
            # Sem a query: ela traz o endereço e a chave.
            sys.stderr.write(f"[fake-maps] {self.command} {urlparse(self.path).path} {code}\n")

        def _json(self, status: int, body: dict) -> None:
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            # O ViaCEP é lido pelo navegador da loja (via ``page.route``): CORS aberto, como o dele.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):  # noqa: N802 — assinatura da stdlib
            url = urlparse(self.path)
            path = url.path.rstrip("/")
            query = {key: values[0] for key, values in parse_qs(url.query).items()}
            if path == "/health":
                return self._json(200, {"ok": True})
            if path == "/maps/api/geocode/json":
                if not query.get("key"):
                    return self._json(200, {"status": "REQUEST_DENIED", "results": [], "error_message": "fake: sem key"})
                if "latlng" in query:
                    return self._json(200, reverse(query["latlng"]))
                return self._json(200, forward(query.get("address", "")))
            match = re.fullmatch(r"/ws/(\d{8})/json", path)
            if match:
                return self._json(200, viacep(match.group(1)))
            sys.stderr.write(f"[fake-maps] ROTA NÃO IMPLEMENTADA: {self.command} {url.path}\n")
            return self._json(404, {"status": "NOT_FOUND", "results": []})

    return Handler


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=12192)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), _handler())
    sys.stderr.write(f"[fake-maps] ouvindo em http://{args.host}:{args.port}\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
