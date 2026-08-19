"""Faixas de hora por OCASIÃO — o vocabulário em que "quem são os clientes" se lê.

Decisão do dono (18/08/2026): faixas por ocasião, não por hora cheia. As
fronteiras estão onde a curva horária de 2025 muda de regime (10h→11h cai,
14h→15h dispara, 17h→18h despenca), mas o corte é de negócio e mora nesta
tupla — trocar de grade é editar aqui, não reescrever nada.

⚠️ A hora é a do REGISTRO da venda (no Yooga, a autorização da NFC-e = o
pagamento), não a hora em que a pessoa sentou. Quem almoça às 13h e paga às
14h05 cai em "Tarde". Com o nome da ocasião essa ressalva precisa aparecer na
tela; o rótulo carrega as horas por isso ("Almoço · 11–14h").

Fora das faixas (antes das 9h, depois das 19h) → balde declarado, nunca some.
"""

from __future__ import annotations

from typing import NamedTuple


class HourBand(NamedTuple):
    key: str
    label: str
    start: int  # hora local, inclusive
    end: int  # hora local, exclusive

    @property
    def hours(self) -> int:
        return self.end - self.start

    @property
    def title(self) -> str:
        if self.end <= self.start:
            return self.label  # "fora do expediente" não tem horas para mostrar
        return f"{self.label} · {self.start}–{self.end}h"


HOUR_BANDS: tuple[HourBand, ...] = (
    HourBand("morning", "Manhã", 9, 11),
    HourBand("lunch", "Almoço", 11, 14),
    HourBand("afternoon", "Tarde", 14, 17),
    HourBand("late", "Fim de dia", 17, 19),
)

OUTSIDE = HourBand("outside", "Fora do expediente", 0, 0)

BAND_KEYS: tuple[str, ...] = tuple(band.key for band in HOUR_BANDS)


def band_for(hour: int) -> HourBand:
    """A faixa de uma hora local — ou "fora do expediente", declarado."""
    for band in HOUR_BANDS:
        if band.start <= hour < band.end:
            return band
    return OUTSIDE


def band_by_key(key: str) -> HourBand | None:
    for band in (*HOUR_BANDS, OUTSIDE):
        if band.key == key:
            return band
    return None
