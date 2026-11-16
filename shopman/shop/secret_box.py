"""Cifra simétrica para segredo de loja guardado no banco.

A chave de cifra é derivada do ``SECRET_KEY`` (HKDF-SHA256), e não de uma
variável nova: o segredo da loja mora no banco (ADR-042) e o único segredo de
ambiente continua sendo o do Django. Consequência que se escreve: trocar o
``SECRET_KEY`` invalida os segredos guardados, e eles precisam ser cadastrados
de novo no Admin. ``open_secret`` devolve vazio nesse caso (com aviso no log),
e a função que depende dele aparece como "não configurada", nunca quebra.
"""

from __future__ import annotations

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings

logger = logging.getLogger(__name__)

_INFO = b"shopman.secret_box.v1"


def _fernet() -> Fernet:
    raw = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(
        str(settings.SECRET_KEY).encode()
    )
    return Fernet(base64.urlsafe_b64encode(raw))


def seal_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def open_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        logger.warning("secret_box: segredo ilegível (SECRET_KEY trocado?); cadastre de novo no Admin")
        return ""
