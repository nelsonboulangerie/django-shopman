"""Quem escreve a ficha técnica, medido nas personas da Nelson (beta 05/11/2026, PROD-09).

Decisão do dono: a Cozinha NÃO cria, edita, confere nem publica ficha. Isso é da
gestão da produção (Gerente e Dono). A Cozinha tem ``shop.manage_production`` para
operar lotes, e antes essa permissão abria o editor de receita por tabela.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command

from shopman.backstage.projections.recipe_book import resolve_recipe_book_access

NELSON = Path(__file__).resolve().parents[3] / "config/instances/nelson.json"

pytestmark = pytest.mark.django_db


def _member_of(name: str, username: str) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    user.groups.add(Group.objects.get(name=name))
    return User.objects.get(pk=user.pk)


def test_cozinha_le_a_ficha_e_so_a_gerencia_escreve(settings):
    settings.SHOPMAN_INSTANCE_DESCRIPTOR = str(NELSON)
    call_command("setup_groups", stdout=StringIO())

    cozinha = _member_of("Cozinha", "diofer")
    gerente = _member_of("Gerente", "joyce")

    assert cozinha.has_perm("shop.manage_production"), "a Cozinha segue operando lotes"
    kitchen_access = resolve_recipe_book_access(cozinha)
    assert (kitchen_access.can_view, kitchen_access.can_edit) == (True, False)

    manager_access = resolve_recipe_book_access(gerente)
    assert (manager_access.can_view, manager_access.can_edit) == (True, True)
