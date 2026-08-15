"""Código de conferência do comprovante.

O papel não pode **ser** a verdade — qualquer um imprime outro. Mas pode
**apontar** para ela: o código resolve para o registro no banco, e um papel
inventado não tem código que resolva.

Assinado com a `SECRET_KEY`, não sequencial: adivinhar o código de um movimento
que não existe exige a chave. Sem isso, bastaria escrever `SG-999` num papel.

⚠️ Isto não impede **fotocópia** de um comprovante legítimo. Torna a fraude
detectável, não impossível. Papel é papel.
"""

from __future__ import annotations

import hashlib
import hmac

from django.conf import settings

PREFIX = "SG"
#: Tamanho da assinatura no papel. 8 caracteres de base32 ≈ 40 bits — o
#: suficiente para tornar chute inviável num balcão, e curto o bastante para
#: alguém digitar quando o QR não lê.
_SIGNATURE_LEN = 8
_ALPHABET = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # sem I/O para não confundir com 1/0


class InvalidReceiptCode(ValueError):
    pass


def code_for(movement_id: int) -> str:
    """Código impresso no comprovante, ex.: ``SG-42-7K3PQR2M``."""
    return f"{PREFIX}-{movement_id}-{_signature(movement_id)}"


def movement_id_from(code: str) -> int:
    """Devolve o id do movimento, ou levanta se o código não confere.

    Comparação em tempo constante: um código inválido não deve revelar, pelo
    tempo de resposta, o quanto acertou.
    """
    partes = str(code or "").strip().upper().split("-")
    if len(partes) != 3 or partes[0] != PREFIX:
        raise InvalidReceiptCode("Código de comprovante malformado.")
    try:
        movement_id = int(partes[1])
    except ValueError as exc:
        raise InvalidReceiptCode("Código de comprovante malformado.") from exc
    if not hmac.compare_digest(partes[2], _signature(movement_id)):
        raise InvalidReceiptCode("Código de comprovante não confere.")
    return movement_id


def _signature(movement_id: int) -> str:
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"cash-movement-receipt:{movement_id}".encode(),
        hashlib.sha256,
    ).digest()
    numero = int.from_bytes(digest[:8], "big")
    saida = []
    for _ in range(_SIGNATURE_LEN):
        numero, resto = divmod(numero, len(_ALPHABET))
        saida.append(_ALPHABET[resto])
    return "".join(saida)
