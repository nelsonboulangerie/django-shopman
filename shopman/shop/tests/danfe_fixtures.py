"""XML fictício compartilhado pelos testes de leitura e transporte da impressão."""

from pathlib import Path

from shopman.shop.services.danfe_xml import parse_authorized_xml

KEY = "41260800000000000000650010000001521151375188"
XML = Path(__file__).with_name("fixtures").joinpath("danfe-authorized.xml").read_bytes()


def xml_for_key(url, key):
    return parse_authorized_xml(XML.replace(KEY.encode(), key.encode()), key)
