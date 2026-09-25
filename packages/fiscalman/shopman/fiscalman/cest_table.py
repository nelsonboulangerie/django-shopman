"""CEST × NCM — a parte do Anexo do Conv. ICMS 142/2018 que o catálogo usa.

O CEST (Código Especificador da Substituição Tributária) **identifica a
mercadoria** no catálogo de segmentos do Convênio; ele não define tributação.
Quem define é o perfil fiscal (CSOSN + CFOP). A lei manda informar o CEST de
todo item listado nos Anexos II a XXVI, com ou sem ST (Conv. 142/2018, cl. 20ª,
I; cl. 3ª para o Simples Nacional; RICMS/PR, Anexo X, art. 1º).

Esta tabela serve ao **aviso** de compatibilidade (:func:`cest_ncm_warnings`),
não a bloqueio: ela não é o Anexo inteiro, é o recorte que a casa pratica. Um
CEST fora dela não é erro — é "confira no Anexo".

Fonte: texto consolidado do Conv. ICMS 142/2018 no CONFAZ,
https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18 (Anexo III
para bebidas não alcoólicas, Anexo XVII para produtos alimentícios), lido em
24/09/2026. Cada linha é ``CEST: (prefixos de NCM que o Anexo lista, descrição)``.
"""

from __future__ import annotations

CEST_NCM: dict[str, tuple[tuple[str, ...], str]] = {
    # ── Anexo III — bebidas não alcoólicas ──
    "0300100": (("2201.10",), "Água mineral ou potável, em garrafa de vidro de até 500 ml"),
    "0300500": (("2201.10",), "Água mineral ou potável, em copo ou embalagem plástica de até 500 ml"),
    "0301000": (("2202.10", "2202.99"), "Refrigerante em vidro descartável"),
    "0301002": (("2202.10", "2202.99"), "Refrigerante em lata"),
    # ── Anexo XVII — produtos alimentícios ──
    "1701000": (("2009",), "Sucos de fruta ou de produtos hortícolas"),
    "1702300": (("0406",), "Requeijão e similares, em recipiente até 1 kg"),
    "1702400": (("0406",), "Queijos"),
    "1702500": (("0405.10",), "Manteiga, em embalagem até 1 kg"),
    "1703800": (("2103.30",), "Mostarda preparada"),
    "1703500": (("2103.90.21", "2103.90.91"), "Condimentos e temperos compostos, inclusive molho de pimenta"),
    "1705000": (("1905.20",), "Pães industrializados, inclusive de especiarias, exceto panetones e bolo de forma"),
    "1705200": (("1905.20.10",), "Panetones"),
    "1705300": (("1905.31",), "Biscoitos e bolachas derivados de farinha de trigo"),
    "1706000": (("1905.90.10",), "Outros pães de forma"),
    "1706200": (("1905.90.90",), "Outros pães"),
    "1707600": (("1601",), "Enchidos (embutidos) e produtos semelhantes, exceto salsicha, linguiça e mortadela"),
    "1707700": (("1601",), "Salsicha e linguiça"),
    "1707904": (("1602.41",), "Preparações e conservas de carne suína: pernas e respectivos pedaços"),
    "1706700": (("1509",), "Azeites de oliva, em recipientes de até 2 litros"),
    "1708701": (("0203", "0206", "0209", "0210.1", "0210.99"), "Carnes e produtos comestíveis do abate de suínos"),
    "1709000": (("2001",), "Produtos hortícolas preparados ou conservados em vinagre"),
    "1709200": (("2005",), "Outros produtos hortícolas preparados ou conservados, exceto em vinagre"),
    "1709400": (("2007",), "Doces, geleias, marmeladas, purês e pastas de frutas"),
    "1709700": (("0902", "1211.90.90", "2106.90.90"), "Chá, mesmo aromatizado"),
}


def _digits(code: str) -> str:
    return "".join(ch for ch in code if ch.isdigit())


def cest_ncm_warnings(ncm: str, cest: str) -> list[str]:
    """Avisos (nunca erros) de CEST incompatível com o NCM. Lista vazia = ok."""
    if not cest:
        return []
    entry = CEST_NCM.get(cest)
    if entry is None:
        return [f"CEST {cest} não está na tabela da casa: confira no Anexo do Conv. ICMS 142/2018."]
    prefixes, description = entry
    ncm_digits = _digits(ncm)
    if ncm_digits and not any(ncm_digits.startswith(_digits(p)) for p in prefixes):
        listed = ", ".join(prefixes)
        return [f"CEST {cest} ({description}) é do NCM {listed}; o produto está no NCM {ncm}."]
    return []
