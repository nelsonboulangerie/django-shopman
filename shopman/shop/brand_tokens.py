"""Tokens de design do storefront, montados a partir da paleta da LOJA.

A paleta é dado da Instância: ``Shop.brand_palette`` (``{"light": {...}, "dark": {...}}``,
cada cor semântica em canais sRGB ``'R G B'``). O produto não carrega paleta de
ninguém. Loja sem paleta gravada emite só fontes e modo de cor, e a superfície veste
os próprios defaults; não há marca de outra instância para cair por cima.

Uso no CSS: `rgb(var(--primary))`; na superfície Nuxt a marca emite `rgb(R G B)` nas
variáveis reais.
"""

from __future__ import annotations


def _rgb_channels_to_hex(channels: str) -> str:
    """'R G B' (0–255) → '#rrggbb'."""
    parts = channels.split()
    if len(parts) != 3:
        return "#808080"
    r, g, b = (max(0, min(255, int(p))) for p in parts)
    return f"#{r:02x}{g:02x}{b:02x}"


def build_storefront_design_tokens(
    *,
    palette: dict | None,
    heading_font: str,
    body_font: str,
    color_mode: str = "light",
) -> dict:
    """
    Dict para `storefront.design_tokens`: cada cor semântica é string **'R G B'** (canais sRGB).

    Light + mapa `dark` espelham os mesmos nomes de token, para Nuxt e Django se vestirem
    de UMA config. `theme_hex` (navbar/PWA) = ``primary``; `background_hex` = ``background``.
    """
    palette = palette or {}
    light = dict(palette.get("light") or {})
    dark = dict(palette.get("dark") or {})

    tokens = {
        **light,
        "dark": dark,
        "color_mode": color_mode,
        "heading_font": heading_font,
        "body_font": body_font,
    }
    if "background" in light:
        tokens["background_hex"] = _rgb_channels_to_hex(light["background"])
    if "primary" in light:
        tokens["theme_hex"] = _rgb_channels_to_hex(light["primary"])
    return tokens
