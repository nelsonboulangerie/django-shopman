"""Geometria raster e ausência segura de marca; sem impressora conectada."""

from PIL import Image

from shopman.backstage.services.print_branding import logo_bytes


def test_logo_dimensions_are_bounded_and_not_inverted(settings, tmp_path):
    image = Image.new("RGB", (600, 200), "black")
    path = tmp_path / "logo.png"
    image.save(path)
    settings.SHOPMAN_PRINT_LOGO_PATH = str(path)
    payload = logo_bytes()
    start = payload.index(b"\x1dv0\x00")
    width = int.from_bytes(payload[start + 4 : start + 6], "little") * 8
    height = int.from_bytes(payload[start + 6 : start + 8], "little")
    assert width <= 192 and height <= 64
    assert payload[start + 8] == 255  # preto = bit 1 na impressora
    assert payload.endswith(b"\x1ba\x00")


def test_unavailable_logo_uses_text_fallback(settings):
    settings.SHOPMAN_PRINT_LOGO_PATH = "/does-not-exist.png"
    assert logo_bytes() == b""
