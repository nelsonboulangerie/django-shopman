"""Camada de ingestão: o que toda fonte externa compartilha.

Cada fonte tem o seu módulo (``yooga.py``, e os que vierem); aqui mora só o
que é igual para todas — a identidade do arquivo e a linguagem dos erros.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


class IngestError(Exception):
    """Base: a importação não aconteceu, e a mensagem diz por quê em português."""


class AlreadyImported(IngestError):
    """O mesmo arquivo (mesmo hash) já entrou nesta origem, e concluiu.

    Não é silêncio nem duplicação: é recusa declarada. Para recarregar do
    zero existe ``--rebuild``.
    """


class InvalidExport(IngestError):
    """O arquivo não é o que o importador espera — aba, coluna ou linha inválida.

    Levantado na FRONTEIRA, antes de gravar qualquer coisa: coluna renomeada
    no export vira este erro com nome da aba e número da linha, não um
    ``KeyError`` no meio do lote.
    """


def sha256_of(path: str | Path) -> str:
    """Hash do arquivo inteiro, em blocos — o export do Yooga passa de 100 MB."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
