"""``fiscal_emit``: ensaio de emissão, nunca nota de verdade.

Laudo 23/10 (F4): o comando marca a intenção fiscal à força e roda o handler
fora da fila. Contra a Focus de produção ele emitia NFC-e com valor fiscal.
"""

from __future__ import annotations

import pytest
from django.core.management import CommandError, call_command

from shopman.shop.fiscal import fiscal_pool

pytestmark = pytest.mark.django_db


class ProductionBackend:
    is_homologation = False

    def emit(self, **kwargs):
        raise AssertionError("fiscal_emit emitiu contra produção")


class UndeclaredBackend:
    """Backend que não diz o ambiente conta como produção (falha fechado)."""

    def emit(self, **kwargs):
        raise AssertionError("fiscal_emit emitiu sem ambiente declarado")


class HomologationBackend(ProductionBackend):
    is_homologation = True


@pytest.fixture
def use_backend(settings):
    def _use(name):
        settings.SHOPMAN_FISCAL_ADAPTER = f"shopman.shop.tests.test_fiscal_emit_command.{name}"
        fiscal_pool.reset()

    yield _use
    fiscal_pool.reset()


@pytest.mark.parametrize("backend", ["ProductionBackend", "UndeclaredBackend"])
def test_refuses_to_run_outside_homologation(use_backend, backend):
    use_backend(backend)

    with pytest.raises(CommandError, match="não está em homologação"):
        call_command("fiscal_emit", "--order", "QUALQUER")


def test_homologation_backend_passes_the_guard(use_backend):
    use_backend("HomologationBackend")

    # Passou da trava: para adiante, no pedido que não existe.
    with pytest.raises(CommandError, match="não encontrado"):
        call_command("fiscal_emit", "--order", "INEXISTENTE")
