import pytest

from shopman.utils.names import split_full_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Pablo Valentini", ("Pablo", "Valentini")),
        ("Pablo", ("Pablo", "")),
        ("  Pablo   Valentini  ", ("Pablo", "Valentini")),
        ("José da Silva Neto", ("José", "da Silva Neto")),
        # A regra erra do lado do sobrenome, nunca do nome (ver docstring).
        ("Ana Maria Silva", ("Ana", "Maria Silva")),
        ("", ("", "")),
        ("   ", ("", "")),
        (None, ("", "")),
    ],
)
def test_split_full_name(raw, expected):
    assert split_full_name(raw) == expected
