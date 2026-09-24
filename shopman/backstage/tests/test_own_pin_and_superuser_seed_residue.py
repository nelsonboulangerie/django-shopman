"""O dono cadastra o próprio PIN, e o PIN do seed some das contas superusuárias.

Duas metades do mesmo buraco, deixado pelo #1022 (superusuário voltou a destravar
o PDV por PIN):

- a migração ``backstage.0073`` apaga o ``PinCredential`` de todo superusuário,
  porque todos são resíduo do seed antigo (o ``1234`` de todo mundo);
- "Criar ou trocar meu PIN" no Admin dá ao dono — e a qualquer staff que vê a
  tela — um PIN temporário para SI MESMO, com troca obrigatória no 1º destrave.
"""

from __future__ import annotations

from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.contrib.admin.models import LogEntry
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from shopman.doorman.models import PinCredential

from shopman.backstage.admin.operators import PinCredentialAdmin
from shopman.backstage.services.operator import (
    PinChangeError,
    issue_own_temp_pin,
    reset_operator_pin,
)

User = get_user_model()

MIGRATION = import_module("shopman.backstage.migrations.0073_superusuario_perde_pin_do_seed")
CHANGELIST = "/admin/doorman/pincredential/"


def _manager(username="gerente"):
    user = User.objects.create_user(username, password="x", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="cashman", codename="manage_operators")
    )
    return User.objects.get(pk=user.pk)


def _request(user, *, htmx=False):
    headers = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    req = RequestFactory().post(f"{CHANGELIST}my-pin/", {"_form_submitted": "on"}, **headers)
    req.user = user
    req.session = SessionStore()
    req._messages = FallbackStorage(req)
    return req


# ── Migração: o PIN do seed sai do superusuário ─────────────────────────────


@pytest.mark.django_db
def test_migracao_apaga_pin_e_cracha_do_superusuario():
    dono = User.objects.create_superuser("admin", password="x")
    PinCredential.set_for(dono, "1234")
    PinCredential.issue_badge(dono)

    MIGRATION.apagar_pin_de_superusuario(global_apps, None)

    assert not PinCredential.objects.filter(user=dono).exists()


@pytest.mark.django_db
def test_migracao_preserva_pin_e_cracha_de_quem_nao_e_superusuario():
    caixa = User.objects.create_user("fran", password="x", is_staff=True)
    PinCredential.set_for(caixa, "1234")
    PinCredential.issue_badge(caixa)

    MIGRATION.apagar_pin_de_superusuario(global_apps, None)

    cred = PinCredential.objects.get(user=caixa)
    assert cred.verify("1234")
    assert cred.badge_hash


def test_migracao_depende_do_doorman_e_volta_sem_efeito():
    migration = MIGRATION.Migration
    assert ("doorman", "0005_verificationcode_delivery_started_at") in migration.dependencies
    (operation,) = migration.operations
    assert operation.reversible


# ── Serviço: PIN temporário só para quem pediu ──────────────────────────────


@pytest.mark.django_db
def test_issue_own_temp_pin_gera_temporario_com_troca_obrigatoria():
    dono = User.objects.create_superuser("admin", password="x")

    temp = issue_own_temp_pin(dono)

    cred = PinCredential.objects.get(user=dono)
    assert cred.must_change
    assert cred.verify(temp)


@pytest.mark.django_db
def test_issue_own_temp_pin_troca_o_pin_antigo_e_nao_toca_em_mais_ninguem():
    gerente = _manager()
    PinCredential.set_for(gerente, "1234")
    outro = User.objects.create_user("fran", password="x", is_staff=True)
    PinCredential.set_for(outro, "5678")

    temp = issue_own_temp_pin(gerente)

    assert not PinCredential.objects.get(user=gerente).verify("1234")
    assert PinCredential.objects.get(user=gerente).verify(temp)
    cred_outro = PinCredential.objects.get(user=outro)
    assert cred_outro.verify("5678")
    assert not cred_outro.must_change


@pytest.mark.django_db
@pytest.mark.parametrize(
    "kwargs",
    [{"is_staff": True, "is_active": False}, {"is_staff": False, "is_active": True}],
    ids=["inativo", "sem-staff"],
)
def test_issue_own_temp_pin_recusa_quem_nao_e_operador(kwargs):
    user = User.objects.create_user("x", password="x", **kwargs)

    with pytest.raises(PinChangeError) as exc:
        issue_own_temp_pin(user)

    assert exc.value.code == "not_operator"
    assert not PinCredential.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_reset_operator_pin_continua_recusando_superusuario():
    dono = User.objects.create_superuser("admin", password="x")

    with pytest.raises(PinChangeError) as exc:
        reset_operator_pin(dono)

    assert exc.value.code == "superuser_target"
    assert not PinCredential.objects.filter(user=dono).exists()


# ── Admin: "Criar ou trocar meu PIN" ────────────────────────────────────────


@pytest.fixture
def model_admin():
    return PinCredentialAdmin(PinCredential, AdminSite())


@pytest.mark.django_db
def test_acao_do_admin_cria_pin_para_quem_clicou_e_mais_ninguem(model_admin):
    dono = User.objects.create_superuser("admin", password="x")
    caixa = User.objects.create_user("fran", password="x", is_staff=True)
    PinCredential.set_for(caixa, "5678")
    req = _request(dono)

    resp = model_admin.issue_own_pin(req)

    assert resp.status_code == 302
    assert resp["Location"] == CHANGELIST
    cred = PinCredential.objects.get(user=dono)
    assert cred.must_change
    # O temporário aparece UMA vez, na mensagem — e é ele que destrava.
    (msg,) = [str(m) for m in get_messages(req)]
    assert "Seu PIN temporário" in msg
    temp = msg.split("): ")[1].split(".")[0]
    assert cred.verify(temp)
    # Ninguém mais foi tocado.
    assert PinCredential.objects.count() == 2
    assert PinCredential.objects.get(user=caixa).verify("5678")
    # E ficou no histórico do Admin.
    assert LogEntry.objects.filter(user=dono, object_id=str(dono.pk)).exists()


@pytest.mark.django_db
def test_acao_do_admin_por_htmx_manda_o_navegador_para_a_lista(model_admin):
    dono = User.objects.create_superuser("admin", password="x")

    resp = model_admin.issue_own_pin(_request(dono, htmx=True))

    assert resp.status_code == 204
    assert resp["HX-Redirect"] == CHANGELIST


@pytest.mark.django_db
def test_acao_do_admin_exige_a_permissao_da_tela(model_admin):
    sem_permissao = User.objects.create_user("bob", password="x", is_staff=True)

    with pytest.raises(PermissionDenied):
        model_admin.issue_own_pin(_request(sem_permissao))

    assert not PinCredential.objects.filter(user=sem_permissao).exists()
    assert model_admin.has_own_pin_permission(_request(_manager()))


def test_acao_esta_no_topo_da_lista_e_nao_na_selecao(model_admin):
    assert "issue_own_pin" in model_admin.actions_list
    assert "issue_own_pin" not in model_admin.actions


@pytest.mark.django_db
def test_resetar_pin_da_linha_do_superusuario_recusa_sem_erro_500(model_admin):
    gerente = _manager()
    dono = User.objects.create_superuser("admin", password="x")
    cred = PinCredential.set_for(dono, "4321")
    req = _request(gerente)

    model_admin.reset_pin(req, PinCredential.objects.filter(pk=cred.pk))

    (msg,) = [str(m) for m in get_messages(req)]
    assert "Criar ou trocar meu PIN" in msg
    assert PinCredential.objects.get(pk=cred.pk).verify("4321")


@pytest.mark.django_db
def test_acao_responde_pela_url_do_admin_e_abre_o_dialogo_no_get(client):
    from shopman.shop.models import Shop

    # Sem Shop o OnboardingMiddleware desvia todo /admin/ para o cadastro da loja.
    Shop.objects.create(name="Nelson")
    dono = _manager()
    client.force_login(dono)

    # O botão mora no topo da lista, sem precisar marcar linha nenhuma.
    lista = client.get(CHANGELIST)
    assert lista.status_code == 200
    assert "Criar ou trocar meu PIN" in lista.content.decode()
    assert f'href="{CHANGELIST}my-pin/"' in lista.content.decode()

    resp = client.get(f"{CHANGELIST}my-pin/")

    # GET só desenha o diálogo de confirmação; nada é gerado sem o POST.
    assert resp.status_code == 200
    assert not PinCredential.objects.filter(user=dono).exists()

    resp = client.post(f"{CHANGELIST}my-pin/", {"_form_submitted": "on"})

    assert resp.status_code == 302
    assert PinCredential.objects.get(user=dono).must_change
