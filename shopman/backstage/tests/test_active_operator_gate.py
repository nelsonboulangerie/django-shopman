"""O gate autoriza contra QUEM ESTÁ OPERANDO — e não existe segundo sujeito.

Este arquivo guardava a garantia de não-bypass da "Opção C": havia duas
identidades (a sessão do aparelho e um operador ativo guardado num dicionário de
sessão), e os testes fixavam que a permissão da primeira não podia vazar para a
segunda.

Com a D1 Parte B (21/08/2026) o problema deixou de existir por construção: quem
prova o PIN VIRA a sessão. Não há como um caminho "esquecer" de perguntar ao
operador, porque não há a quem mais perguntar — e era assim que o buraco nascia,
num punhado de caminhos que ainda consultavam o aparelho.

O que estes testes guardam agora é a fronteira nova: **estação confiável não
autoriza nada.** Ela diz de onde a requisição veio, e mais nada.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from rest_framework.test import APIRequestFactory

from shopman.backstage.api.permissions import (
    STATION_LOCKED_CODE,
    HasBackstagePermission,
    IsTrustedStation,
)

User = get_user_model()
PERM = "backstage.operate_production"


class _View:
    required_permission = PERM


def _grant(user) -> None:
    app_label, codename = PERM.split(".")
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label=app_label, codename=codename)
    )
    user.refresh_from_db()


def _req(user=None, *, estacao: str = ""):
    """Uma requisição com (ou sem) alguém logado, vinda (ou não) de uma estação."""
    request = APIRequestFactory().get("/x")
    request.user = user or AnonymousUser()
    request.COOKIES = {}
    if estacao:
        request.COOKIES[f"doorman_dt_station_{estacao}"] = "token-que-o-teste-nao-valida"
    return request


@pytest.fixture
def operador(db):
    user = User.objects.create_user("joyce", password="x", is_staff=True)
    _grant(user)
    return User.objects.get(pk=user.pk)


@pytest.mark.django_db
def test_quem_esta_logado_com_a_permissao_passa(operador):
    assert HasBackstagePermission().has_permission(_req(operador), _View()) is True


@pytest.mark.django_db
def test_quem_esta_logado_SEM_a_permissao_nao_passa(db):
    sem_perm = User.objects.create_user("bia", password="x", is_staff=True)

    gate = HasBackstagePermission()

    assert gate.has_permission(_req(sem_perm), _View()) is False
    # Recusa por permissão, não por trava: a tela não deve pedir PIN aqui.
    assert gate.code != STATION_LOCKED_CODE


@pytest.mark.django_db
def test_usuario_que_nao_e_da_casa_nao_passa(db):
    """`is_staff=False` é cliente da loja — nunca opera, nem com a permissão."""
    cliente = User.objects.create_user("fulano", password="x", is_staff=False)
    _grant(cliente)

    assert HasBackstagePermission().has_permission(_req(cliente), _View()) is False


@pytest.mark.django_db
def test_usuario_inativo_nao_passa(operador):
    operador.is_active = False
    operador.save(update_fields=["is_active"])

    assert HasBackstagePermission().has_permission(_req(operador), _View()) is False


@pytest.mark.django_db
def test_ninguem_logado_nao_passa(db):
    assert HasBackstagePermission().has_permission(_req(), _View()) is False


@pytest.mark.django_db
def test_ESTACAO_CONFIAVEL_SOZINHA_NAO_AUTORIZA_NADA(db, monkeypatch):
    """A fronteira inteira, num teste: a chave abre a antessala, não o cofre.

    É o que separa este desenho do anterior. Antes, ser "o aparelho do balcão"
    significava ter uma sessão Django — no staging, a do `admin` superusuário —
    e portanto TODAS as permissões. Agora ser o aparelho não dá nenhuma.
    """
    monkeypatch.setattr(
        "shopman.backstage.api.permissions.is_trusted_station", lambda request: True
    )
    gate = HasBackstagePermission()

    assert gate.has_permission(_req(estacao="balcao"), _View()) is False
    # E a recusa se identifica, para a tela pedir PIN em vez de desenhar vazio.
    assert gate.code == STATION_LOCKED_CODE


@pytest.mark.django_db
def test_a_estacao_abre_a_ANTESSALA_e_so(db, monkeypatch):
    """`IsTrustedStation` é o gate do destrave: sem ele a loja não abriria de manhã.

    Com uma identidade só, o balcão travado não tem ninguém logado. Se o
    endpoint que recebe o PIN exigisse sessão, ninguém conseguiria criar uma.
    """
    monkeypatch.setattr(
        "shopman.backstage.api.permissions.is_trusted_station", lambda request: True
    )

    assert IsTrustedStation().has_permission(_req(estacao="balcao"), _View()) is True
    # E um aparelho qualquer da rua não entra nem na antessala.
    monkeypatch.setattr(
        "shopman.backstage.api.permissions.is_trusted_station", lambda request: False
    )
    assert IsTrustedStation().has_permission(_req(), _View()) is False


@pytest.mark.django_db
def test_sem_permissao_declarada_basta_ser_da_casa(operador):
    class _SemPerm:
        required_permission = None

    assert HasBackstagePermission().has_permission(_req(operador), _SemPerm()) is True


@pytest.mark.django_db
def test_tupla_de_permissoes_exige_TODAS(operador):
    class _Duas:
        required_permission = (PERM, "cashman.audit_shift")

    assert HasBackstagePermission().has_permission(_req(operador), _Duas()) is False
