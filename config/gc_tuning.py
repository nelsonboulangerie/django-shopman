"""Coleta de lixo do processo web, ajustada depois do boot.

Por que existe: no ar (01/10/2026) o ``gc;dur`` do Server-Timing fica em geral
abaixo de 10 ms, com picos de 265–325 ms. Os picos são coletas completas (geração
2), que percorrem TODOS os objetos rastreados do processo, e a maior parte deles
é o próprio boot: módulos, classes, URLconf, settings, registries. Nada disso
vira lixo enquanto o processo vive.

Dois ajustes, cada um por env:

- ``SHOPMAN_GC_FREEZE`` (padrão ``1``, ligado): depois do boot, carrega a URLconf
  (que importa as views), coleta uma vez e chama ``gc.freeze()``. Os objetos do
  boot vão para a geração permanente e a coleta completa deixa de percorrê-los.
- ``SHOPMAN_GC_THRESHOLD`` (padrão vazio = limiares do Python, 700/10/10): ex.
  ``"5000,10,10"`` para ``gc.set_threshold``. Fica desligado de propósito: na
  bancada, limiar maior soma MENOS tempo de GC mas faz pausas MAIORES (a geração
  jovem cresce e cada coleta dela custa mais), e o que se quer cortar é o pico.

Bancada de 01/10/2026 (daphne, 600 GETs em 4 conexões sobre shell/home/catalog/
menu/public-catalog), pausa máxima de uma coleta / soma das coletas:

- sem ajuste: 86 ms / 1,82 s (19 coletas completas de ~73 ms);
- freeze: 9,7 ms / 0,63 s;
- freeze + 5000,10,10: 23,9 ms / 0,46 s;
- freeze + 50000,20,10: 76,6 ms / 0,41 s.

``0``/``false``/``off`` desliga o freeze. Um limiar inválido é ignorado com aviso
no log: GC é desempenho, não correção, e o boot não cai por causa dele.
"""

from __future__ import annotations

import gc
import logging
import os
from collections.abc import Mapping

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = ""
_OFF = {"0", "false", "no", "off"}


def _parse_threshold(raw: str) -> tuple[int, ...] | None:
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if not 1 <= len(parts) <= 3:
        return None
    try:
        values = tuple(int(part) for part in parts)
    except ValueError:
        return None
    if any(value < 0 for value in values):
        return None
    return values


def _warm_urlconf() -> None:
    """Importa a URLconf (e com ela as views) antes do freeze."""
    from django.urls import get_resolver

    get_resolver().url_patterns  # noqa: B018 - o acesso força o import


def tune_gc_after_boot(environ: Mapping[str, str] = os.environ) -> dict:
    """Aplica limiar e freeze. Chamar depois de ``get_asgi_application()``.

    Devolve o que foi aplicado (para log e teste).
    """
    applied: dict = {"threshold": None, "frozen": 0}

    raw_threshold = environ.get("SHOPMAN_GC_THRESHOLD", DEFAULT_THRESHOLD).strip()
    if raw_threshold:
        threshold = _parse_threshold(raw_threshold)
        if threshold is None:
            logger.warning("gc_tuning: SHOPMAN_GC_THRESHOLD=%r inválido; mantido %s", raw_threshold, gc.get_threshold())
        else:
            gc.set_threshold(*threshold)
            applied["threshold"] = gc.get_threshold()

    if environ.get("SHOPMAN_GC_FREEZE", "1").strip().lower() not in _OFF:
        try:
            _warm_urlconf()
        except Exception:  # noqa: BLE001 - o boot não cai por desempenho; o erro de URLconf aparece no 1º request
            logger.warning("gc_tuning: URLconf não carregou antes do freeze", exc_info=True)
        gc.collect()
        gc.freeze()
        applied["frozen"] = gc.get_freeze_count()

    logger.info("gc_tuning: threshold=%s frozen=%s", gc.get_threshold(), applied["frozen"])
    return applied
