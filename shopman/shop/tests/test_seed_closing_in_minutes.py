"""`seed --closing-in-minutes N`: a casa que fecha daqui a pouco, só na pilha de teste (J5, #2686).

A jornada J5 precisa do checkout aberto atravessando o fechamento. A pilha de teste passa a
opção ao seed; nada que vai ao ar lê isto. O efeito em si (hoje das 0h até agora + N) é
provado pela própria J5, que roda o seed inteiro; aqui ficam as recusas, baratas.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings


@pytest.mark.django_db
def test_never_in_production():
    with override_settings(SHOPMAN_ENVIRONMENT="production"):
        with pytest.raises(CommandError, match="só de pilha de teste"):
            call_command("seed", "--closing-in-minutes", "5")


@pytest.mark.django_db
def test_needs_at_least_one_minute():
    with override_settings(SHOPMAN_ENVIRONMENT="development"):
        with pytest.raises(CommandError, match="1 ou mais"):
            call_command("seed", "--closing-in-minutes", "0")
