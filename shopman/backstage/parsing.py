"""Dialeto de ENTRADA das APIs de operador.

A casa tem dialeto de **saída** disciplinado desde sempre — ``{detail, field,
errors}``, com ``EXCEPTION_HANDLER`` ligado e referência escrita
(``shopman/shop/api_errors.py``, ``docs/reference/errors.md``). A **entrada** não
tinha dono, e três dialetos conviviam:

1. ``bool(...)`` cru — e ``bool("false")`` é ``True``. Um cliente que mande
   ``{"checked": "false"}`` marca o item em vez de desmarcar, e nada avisa.
2. ``_as_bool``, o parser certo, escrito uma vez em ``api/marketing.py`` e usado
   em **um** call site do próprio arquivo.
3. ``_as_int`` duplicado em ``api/marketing.py`` e ``api/catalog.py``, os dois
   engolindo ``TypeError``/``ValueError`` e devolvendo ``None`` — lixo entra, vira
   ``None``, e o ``None`` segue viagem sem 400.

Nenhum desses é explorável pelo operador com a UI de hoje, que manda JSON de
verdade. Todos são explotáveis por quem fala com a API direto, e todos viram bug
real no dia em que alguém trocar um ``fetch`` por ``URLSearchParams``, ou num
cliente de integração. É dívida de superfície de ataque, não bug de tela.

**A régua aqui é a da casa:** falhar fechado, ou falhar gritando. Nunca falhar
aberto e calado. Entrada que não dá para interpretar levanta ``ValidationError``
com ``field``, cai no ``EXCEPTION_HANDLER`` e chega ao front como 400 no dialeto
canônico — o mesmo que o resto do sistema já fala.

## O que passa

``as_bool`` aceita o booleano JSON de verdade (o que as superfícies mandam) e os
tokens de string **inequívocos** — ``"true"/"false"``, ``"1"/"0"``, ``"yes"/"no"``,
``"on"/"off"``, sem diferenciar caixa nem espaço em volta. Aceitar a string é
decisão antiga e deliberada da casa (o ``_as_bool`` original documentava
"form-data manda ``"true"``"); o que muda é que ``"false"`` agora vale **False** em
vez de True, e que ``"talvez"`` vira 400 em vez de virar True em silêncio.

Ausência e ``null`` são a mesma coisa: usam o ``default`` quando o call site
declarou um, e viram 400 quando não. Um campo obrigatório que chega vazio é
pergunta sem resposta, não resposta negativa.
"""

from __future__ import annotations

from typing import Any

from rest_framework.exceptions import ValidationError

__all__ = ["as_bool", "as_int"]

_MISSING = object()

_NAO_E_NUMERO = "Este campo espera um número."

_TRUE_TOKENS = frozenset({"true", "1", "yes", "on"})
_FALSE_TOKENS = frozenset({"false", "0", "no", "off"})


def _fail(field: str, message: str):
    # `field` nomeado é o que permite ao front focar o campo certo em vez de
    # mostrar um toast solto (ver docs/reference/errors.md).
    raise ValidationError({field: [message]})


def _absent(data: Any, field: str, default: Any):
    if default is _MISSING:
        _fail(field, "Este campo é obrigatório.")
    return default


def as_bool(data: Any, field: str, *, default: Any = _MISSING, message: str = "") -> bool:
    """Booleano estrito de ``data[field]``.

    ``True``/``False`` JSON passam. ``"true"``, ``"1"``, ``"yes"``, ``"on"`` (e os
    pares negativos) passam, sem diferenciar caixa. ``1``/``0`` passam. Qualquer
    outra coisa — ``"talvez"``, ``2``, ``[]``, ``{}`` — é 400 com ``field``.

    Sem ``default``, ausência e ``null`` também são 400.

    ``message`` troca o texto da recusa por valor inválido. Existe porque em
    alguns campos a casa já escreveu copy melhor que a genérica, e trocar boa
    mensagem de operador por uniformidade seria o pior lado da troca.
    """
    if not isinstance(data, dict) or field not in data:
        return bool(_absent(data, field, default))

    value = data[field]
    if value is None:
        return bool(_absent(data, field, default))
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().lower()
        if token in _TRUE_TOKENS:
            return True
        if token in _FALSE_TOKENS:
            return False
    elif isinstance(value, int) and value in (0, 1):
        # `isinstance(True, int)` é verdade em Python, por isso o bool vem antes.
        return bool(value)

    _fail(field, message or "Este campo aceita apenas sim ou não.")
    raise AssertionError("inalcançável")  # pragma: no cover


def as_int(
    data: Any,
    field: str,
    *,
    default: Any = _MISSING,
    min_value: int | None = None,
    max_value: int | None = None,
    message: str = "",
) -> int | None:
    """Inteiro estrito de ``data[field]``, com faixa opcional.

    Substitui os dois ``_as_int`` duplicados, que devolviam ``None`` para lixo e
    deixavam o ``None`` seguir viagem. Aqui lixo é 400 na porta de entrada, com o
    campo nomeado — e a faixa é conferida no mesmo lugar, para o call site não
    precisar repetir a checagem (e esquecer dela).

    ``True``/``False`` NÃO valem como inteiro: ``int(True)`` é 1 em Python, e
    aceitar isso deixaria um booleano trocado passar por um campo numérico.
    """
    if not isinstance(data, dict) or field not in data:
        return _coerce_range(_absent(data, field, default), field, min_value, max_value)

    value = data[field]
    if value is None or (isinstance(value, str) and not value.strip()):
        return _coerce_range(_absent(data, field, default), field, min_value, max_value)
    if isinstance(value, bool):
        _fail(field, message or _NAO_E_NUMERO)
    if isinstance(value, int):
        return _coerce_range(value, field, min_value, max_value)
    if isinstance(value, str):
        try:
            return _coerce_range(int(value.strip()), field, min_value, max_value)
        except ValueError:
            _fail(field, message or _NAO_E_NUMERO)

    _fail(field, message or _NAO_E_NUMERO)
    raise AssertionError("inalcançável")  # pragma: no cover


def _coerce_range(value, field: str, min_value: int | None, max_value: int | None):
    # O default do call site passa por aqui de propósito: um default fora da
    # faixa é bug de quem chamou, e é melhor descobrir no teste que na produção.
    if value is None:
        return None
    if min_value is not None and value < min_value:
        _fail(field, f"O menor valor aceito é {min_value}.")
    if max_value is not None and value > max_value:
        _fail(field, f"O maior valor aceito é {max_value}.")
    return value
