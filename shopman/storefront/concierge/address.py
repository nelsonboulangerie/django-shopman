"""O endereço da entrega montado NA CONVERSA, parte por parte.

Decisão do dono (25/09/2026): a entrega pelo WhatsApp não manda o cliente
para o site completar o endereço. A nota da entrega a domicílio exige rua,
número, bairro, cidade, UF e CEP separados (``delivery_fiscal_identity``, a
régua do #1118), e o concierge chega lá por três portas:

- **a localização** (pin do WhatsApp): a geocodificação reversa do servidor
  (``geocoding.reverse_geocode``, o mesmo serviço do botão "usar minha
  localização" da loja) devolve rua, bairro, cidade, UF e CEP. O NÚMERO que
  ela devolve é interpolado pelo Google a partir do ponto e não entra: o
  número é o que o cliente diz. A coordenada da entrega é a do pin;
- **o texto**: a geocodificação direta (``geocoding.forward_geocode_structured``)
  separa as partes do que o cliente escreveu e dá a coordenada da taxa;
- **as partes ditas depois** ("é o 45", "apto 12", "o CEP é 86010-000"):
  entram por cima do que já está na sacola, e o que o cliente diz vence o
  que o Google deduziu.

O que falta é perguntado com a MESMA régua da porta do pedido
(``recipient_gaps``), nunca com uma cópia dela.
"""

from __future__ import annotations

import logging
import unicodedata

logger = logging.getLogger(__name__)

#: Parâmetro da ferramenta → chave de ``delivery_address_structured``.
PART_KEYS = {
    "street": "route",
    "street_number": "street_number",
    "complement": "complement",
    "neighborhood": "neighborhood",
    "postal_code": "postal_code",
    "city": "city",
    "state": "state_code",
}

#: Partes que mudam ONDE fica o endereço (e, portanto, a coordenada da taxa).
_LOCATING_KEYS = ("route", "street_number", "neighborhood", "postal_code", "city", "state_code")

#: As chaves do endereço estruturado que esta montagem escreve.
_STRUCTURED_KEYS = (
    "route", "street_number", "complement", "neighborhood", "city", "state_code",
    "postal_code", "place_id", "formatted_address", "latitude", "longitude",
    "is_verified", "coordinates_source",
)

#: "Não tem complemento", dito de algumas formas. Vira ``complement == ""``
#: gravado: a pergunta foi respondida (ausente = ainda não perguntado).
_NO_COMPLEMENT = frozenset({
    "sem", "sem complemento", "nenhum", "nao", "nao tem", "nao ha", "-", "nada", "n/a",
})
_NO_NUMBER = frozenset({"sn", "s/n", "s n", "sem numero", "sem nº", "sem n"})

PIN = "pin"
GEOCODED = "geocoded"


class AddressNotLocated(Exception):
    """O endereço não tem coordenada: sem ela não há taxa honesta."""


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return " ".join(text.casefold().split()).strip(" .")


def _clean(value) -> str:
    return " ".join(str(value or "").split()).strip()


def _postal_code(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return f"{digits[:5]}-{digits[5:]}" if len(digits) == 8 else _clean(value)


def normalize_parts(parts: dict) -> dict:
    """As partes ditas pelo cliente, com as chaves do endereço estruturado.

    Vazio = não informado nesta chamada (não apaga). ``complement`` "sem
    complemento" grava ``""`` (respondido); número "sem número" grava ``S/N``,
    que a nota aceita quando dito explicitamente.
    """
    out: dict = {}
    for param, key in PART_KEYS.items():
        raw = _clean(parts.get(param))
        if not raw:
            continue
        if key == "complement":
            out[key] = "" if _fold(raw) in _NO_COMPLEMENT else raw
        elif key == "street_number":
            out[key] = "S/N" if _fold(raw) in _NO_NUMBER else raw
        elif key == "postal_code":
            out[key] = _postal_code(raw)
        elif key == "state_code":
            out[key] = raw.upper()
        else:
            out[key] = raw
    return out


def formatted(structured: dict) -> str:
    """O endereço numa linha, montado das partes: é o que o entregador lê."""
    street = ", ".join(p for p in (structured.get("route"), structured.get("street_number")) if p)
    complement = structured.get("complement") or ""
    first = f"{street} - {complement}" if street and complement else street or complement
    city = " - ".join(p for p in (structured.get("city"), structured.get("state_code")) if p)
    second = ", ".join(p for p in (structured.get("neighborhood"), city) if p)
    head = " - ".join(p for p in (first, second) if p)
    postal = structured.get("postal_code") or ""
    return ", ".join(p for p in (head, f"CEP {postal}" if postal else "") if p)


def _from_pin(latitude: float, longitude: float) -> dict:
    from shopman.shop.services.geocoding import GeocodingError, reverse_geocode

    base: dict = {}
    try:
        result = reverse_geocode(latitude, longitude)
    except GeocodingError:
        # A falha já virou alerta de integração dentro do serviço. O pin
        # continua valendo (a taxa sai da coordenada): o cliente dita as partes.
        logger.info("concierge.address pin_reverse_unavailable")
    else:
        base = {
            key: value
            for key, value in result.to_dict().items()
            if key in ("route", "neighborhood", "city", "state_code", "postal_code", "place_id") and value
        }
    # O número do reverso é interpolado pelo Google a partir do ponto: não é
    # o número da casa. A coordenada é a do pin, não a do resultado.
    base.update(latitude=float(latitude), longitude=float(longitude), coordinates_source=PIN)
    return base


def _from_text(text: str) -> dict:
    from shopman.shop.services.geocoding import forward_geocode_structured

    result = forward_geocode_structured(text)
    if result is None:
        return {}
    data = result.to_dict()
    base = {
        key: data[key]
        for key in ("route", "street_number", "neighborhood", "city", "state_code", "postal_code", "place_id")
        if data.get(key)
    }
    base.update(latitude=data["latitude"], longitude=data["longitude"], coordinates_source=GEOCODED)
    return base


def compose(*, current: dict | None, pin: tuple[float, float] | None, text: str, parts: dict) -> dict:
    """O endereço estruturado da entrega depois desta chamada.

    ``pin`` recomeça pela localização; ``text`` recomeça pelo texto; nenhum dos
    dois continua o que já está na sacola (``current``). ``parts`` vão por
    cima. Levanta ``AddressNotLocated`` quando não há coordenada.
    """
    said = normalize_parts(parts)
    text = _clean(text)
    if pin is not None:
        base = _from_pin(*pin)
    elif text:
        base = _from_text(text)
        if not base:
            raise AddressNotLocated(text)
    else:
        base = {key: value for key, value in (current or {}).items() if key in _STRUCTURED_KEYS}

    structured = {**base, **said}
    changed = [key for key in _LOCATING_KEYS if key in said and said[key] != base.get(key)]
    if "route" in said and said["route"] != base.get("route"):
        structured.pop("place_id", None)
    if changed and structured.get("coordinates_source") != PIN:
        # O cliente corrigiu onde fica: a coordenada da taxa segue a correção.
        # O pin não se move — é onde a pessoa está e o que o entregador abre.
        from shopman.shop.services.geocoding import forward_geocode

        coords = forward_geocode(formatted({**structured, "complement": ""}))
        if coords:
            structured["latitude"], structured["longitude"] = coords
            structured["coordinates_source"] = GEOCODED
        elif "route" in changed or "city" in changed:
            # Outra rua sem coordenada: a taxa antiga seria de outro lugar.
            structured.pop("latitude", None)
            structured.pop("longitude", None)
    if "latitude" not in structured:
        raise AddressNotLocated(formatted(structured))
    structured["formatted_address"] = formatted(structured)
    structured["is_verified"] = False
    return structured


def gaps(structured: dict) -> list:
    """As lacunas de endereço pela régua da nota (``recipient_gaps``)."""
    from shopman.shop.services import delivery_fiscal_identity as identity

    return [gap for gap in identity.recipient_gaps(tax_id="", address=structured) if gap.field == identity.ADDRESS_FIELD]


def missing_words(structured: dict) -> list[str]:
    from shopman.shop.services import delivery_fiscal_identity as identity

    return identity.address_gap_words(gaps(structured))


def question(structured: dict, *, from_pin: bool) -> str:
    """A pergunta ao cliente sobre o endereço, ou ``""`` quando está completo.

    Uma pergunta por mensagem: o que falta para a nota primeiro; o complemento
    (opcional para a nota, decisivo para o entregador) quando o resto fechou.
    Vindo da localização, o que ela deu é mostrado para o cliente conferir.
    """
    from shopman.shop.services import delivery_fiscal_identity as identity

    words = identity.join_words(missing_words(structured))
    seen = formatted({**structured, "street_number": "", "complement": ""}) if from_pin else ""
    prefix = f"Pela sua localização: {seen}. " if seen else ""
    if words and seen:
        return f"{prefix}Se estiver certo, me diga {words}."
    if words:
        return f"Para a entrega, me diga {words}."
    if "complement" not in structured:
        return f"{prefix}Tem complemento (apartamento, bloco, fundos)? Se não tiver, é só dizer \"sem complemento\"."
    return ""
