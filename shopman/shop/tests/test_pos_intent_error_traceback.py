"""``PosIntentError`` tem que atravessar um ``@contextmanager`` inteira.

Com ``frozen=True``, o ``__exit__`` do ``contextlib`` (Python 3.12) faz
``exc.__traceback__ = tb`` e a dataclass congelada estoura
``FrozenInstanceError`` — o 422 com ``code``/``field`` virava 500 sob
``OperationalObservationMixin``. A exceção original tem que sair intacta.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from shopman.shop.services.pos_intent import PosIntentError


@contextmanager
def _observacao():
    """Um gêmeo mínimo do mixin de observação: só passa o erro adiante."""
    try:
        yield
    except Exception:
        raise


def test_o_erro_original_sai_intacto_de_um_contextmanager():
    with pytest.raises(PosIntentError) as capturado, _observacao():
        raise PosIntentError(code="tab_missing", message="Comanda não encontrada.", field="tab_ref", status=422)

    erro = capturado.value
    assert erro.code == "tab_missing"
    assert erro.field == "tab_ref"
    assert erro.status == 422
    assert str(erro) == "Comanda não encontrada."
    assert erro.__traceback__ is not None


def test_as_duas_instancias_iguais_continuam_distintas_como_toda_excecao():
    a = PosIntentError(code="x", message="m")
    b = PosIntentError(code="x", message="m")

    assert a is not b
    assert {a, b} == {a, b}  # hash por identidade, como ValueError
