"""Um `.mmdb` de verdade, montado byte a byte, para os testes que precisam de um.

O `maxminddb` só LÊ: não há escritor instalado, e versionar um binário de 60 MB para
conferir um inteiro seria troca péssima. O formato é público e o cabeçalho é pequeno,
então quem precisa de uma base com data controlada constrói a sua.

Mora aqui, e não dentro de um arquivo de teste, porque tem dois consumidores: o serviço
(`shopman/shop/tests/test_ip_location.py`) e o comando que alerta
(`shopman/backstage/tests/test_geoip_freshness.py`). É o mesmo arranjo do
`shopman/backstage/tests/certificate_fixtures.py`.

⚠️ A base que sai daqui **não responde consulta nenhuma** — a árvore tem zero nós. Ela
serve para a pergunta "qual a data desta base?", e é só para isso que deve ser usada.
"""

from __future__ import annotations

_MARCADOR = b"\xab\xcd\xefMaxMind.com"


def _controle(tipo: int, tamanho: int) -> bytes:
    """O byte de controle: 3 bits de tipo, 5 de tamanho — e o tipo estendido logo após."""
    saida = bytearray()
    if tipo < 8:
        cabeca, estendido = tipo, b""
    else:
        cabeca, estendido = 0, bytes([tipo - 7])
    if tamanho < 29:
        saida.append((cabeca << 5) | tamanho)
    elif tamanho < 285:
        saida.append((cabeca << 5) | 29)
        saida.append(tamanho - 29)
    else:
        saida.append((cabeca << 5) | 30)
        saida += (tamanho - 285).to_bytes(2, "big")
    return bytes(saida) + estendido


def _inteiro(tipo: int, valor: int) -> bytes:
    # Inteiro no formato é big-endian SEM zeros à esquerda: o zero ocupa zero byte.
    corpo = valor.to_bytes((valor.bit_length() + 7) // 8, "big") if valor else b""
    return _controle(tipo, len(corpo)) + corpo


def _texto(valor: str) -> bytes:
    corpo = valor.encode("utf-8")
    return _controle(2, len(corpo)) + corpo


def _mapa(pares) -> bytes:
    saida = _controle(7, len(pares))
    for chave, valor in pares:
        saida += _texto(chave) + valor
    return saida


def _lista(itens) -> bytes:
    saida = _controle(11, len(itens))
    for item in itens:
        saida += item
    return saida


def mmdb_minimo(build_epoch: int) -> bytes:
    metadados = _mapa(
        [
            ("node_count", _inteiro(6, 0)),
            ("record_size", _inteiro(5, 24)),
            ("ip_version", _inteiro(5, 6)),
            ("database_type", _texto("GeoLite2-City")),
            ("languages", _lista([_texto("en"), _texto("pt-BR")])),
            ("binary_format_major_version", _inteiro(5, 2)),
            ("binary_format_minor_version", _inteiro(5, 0)),
            ("build_epoch", _inteiro(9, build_epoch)),
            ("description", _mapa([("en", _texto("fixture de teste"))])),
        ]
    )
    # Árvore vazia (node_count = 0) + os 16 bytes que separam árvore e seção de dados.
    return b"\x00" * 16 + _MARCADOR + metadados
