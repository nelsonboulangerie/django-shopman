"""Código de conferência do comprovante.

O papel não pode **ser** a verdade — qualquer um imprime outro. Mas pode
**apontar** para ela: o código resolve para o registro no banco, e um papel
inventado não tem código que resolva.

Assinado com a `SECRET_KEY`, não sequencial: adivinhar o código de um lançamento
que não existe exige a chave. Sem isso, bastaria escrever `SG-999` num papel.
O número do código é o ``pk`` da linha ``cash_out``/``cash_in`` no livro
(``cashman.Entry``).

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


def code_for(entry_id: int) -> str:
    """Código impresso no comprovante, ex.: ``SG-42-7K3PQR2M``.

    Assina sempre com a chave **atual**. Papel novo nasce com a assinatura de
    hoje; papel velho continua conferindo pelas chaves antigas (ver
    ``entry_id_from``).
    """
    return f"{PREFIX}-{entry_id}-{_signature(entry_id, settings.SECRET_KEY)}"


def entry_id_from(code: str) -> int:
    """Devolve o id do lançamento, ou levanta se o código não confere.

    Comparação em tempo constante: um código inválido não deve revelar, pelo
    tempo de resposta, o quanto acertou.
    """
    parts = str(code or "").strip().upper().split("-")
    if len(parts) != 3 or parts[0] != PREFIX:
        raise InvalidReceiptCode("Código de comprovante malformado.")
    try:
        entry_id = int(parts[1])
    except ValueError as exc:
        raise InvalidReceiptCode("Código de comprovante malformado.") from exc
    # ⚠️ Sem as chaves antigas, girar a SECRET_KEY (o que se faz depois de um
    # vazamento, e é a receita do próprio Django) transformaria em "não confere"
    # TODO comprovante já impresso e guardado na gaveta — meses de papel de
    # auditoria virando lixo por causa de uma troca de chave. `SECRET_KEY_FALLBACKS`
    # é o mecanismo que o Django tem exatamente para essa janela.
    accepted = [settings.SECRET_KEY, *getattr(settings, "SECRET_KEY_FALLBACKS", [])]
    # Sem short-circuit: comparar contra todas as chaves sempre custa o mesmo, e
    # o tempo de resposta não conta a ninguém qual delas acertou.
    matches = False
    for key in accepted:
        matches |= hmac.compare_digest(parts[2], _signature(entry_id, key))
    if not matches:
        raise InvalidReceiptCode("Código de comprovante não confere.")
    return entry_id


def _signature(entry_id: int, secret: str) -> str:
    # O rótulo dentro do HMAC é constante de protocolo, não nome: trocá-lo
    # invalidaria todo papel já impresso sem ganhar nada.
    digest = hmac.new(
        secret.encode("utf-8"),
        f"cash-movement-receipt:{entry_id}".encode(),
        hashlib.sha256,
    ).digest()
    number = int.from_bytes(digest[:8], "big")
    out = []
    for _ in range(_SIGNATURE_LEN):
        number, rest = divmod(number, len(_ALPHABET))
        out.append(_ALPHABET[rest])
    return "".join(out)
