"""A cor de promoção da marca Nelson passa o AA nos dois temas (X9, OC-30).

O texto de promoção ("Semana do Pão -15%") tem 14 px; a cor é o significado e não pode
virar branco no tema escuro. A paleta dá um ``promotion`` por tema, e ele precisa de 4,5:1
contra o fundo e o cartão de cada tema, onde a promoção aparece.
"""

import pytest

from config.brand_palette_nelson import NELSON_BRAND_PALETTE


def _luminance(channels: str) -> float:
    def lin(v: int) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(part) for part in channels.split())
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("surface", ["background", "card"])
def test_promotion_text_passes_aa_on_every_surface(mode, surface):
    palette = NELSON_BRAND_PALETTE[mode]
    assert _contrast(palette["promotion"], palette[surface]) >= 4.5


def test_dark_promotion_is_the_darkest_burgundy_that_passes():
    # O primary escuro (o burgundy da ação) reprova; o Burgundy-300 da escala passa.
    dark = NELSON_BRAND_PALETTE["dark"]
    assert _contrast(dark["primary"], dark["background"]) < 4.5
    assert dark["promotion"] == "185 123 130"
    assert _contrast("157 88 96", dark["background"]) < 4.5  # Burgundy-400, um degrau abaixo
