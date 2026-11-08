"""Tolerância do caixa no Terminal: só o Dono edita (decisão do dono, 06/11/2026).

Beta test 05/11/2026, ADM-05: a Gerente (``cashman.change_terminal``, sem
``cashman.audit_shift``) mudava a "Tolerância do caixa" do terminal no Admin. A
tolerância decide o veredito da apuração, que é de quem audita. A Gerente segue
editando o resto do terminal (gaveta, impressora), mas a tolerância fica só
leitura para ela e o POST não a altera.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.test import RequestFactory
from django.urls import reverse
from shopman.cashman.models import Terminal

pytestmark = pytest.mark.django_db

TOLERANCIA = {"percent": "1", "min_q": 300, "max_q": 1500}


@pytest.fixture(autouse=True)
def _shop():
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")


def _perms(user, *labels):
    for label in labels:
        app_label, codename = label.split(".")
        user.user_permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))
    return User.objects.get(pk=user.pk)


@pytest.fixture
def gerente():
    user = User.objects.create_user("gerente-tolerancia", password="pw", is_staff=True)
    return _perms(user, "cashman.view_terminal", "cashman.change_terminal", "cashman.adjust_shift")


@pytest.fixture
def dono():
    user = User.objects.create_user("dono-tolerancia", password="pw", is_staff=True)
    return _perms(user, "cashman.view_terminal", "cashman.change_terminal", "cashman.audit_shift")


@pytest.fixture
def terminal():
    return Terminal.objects.create(
        ref="t-tol", label="Caixa 1", channel_ref="pdv", metadata={"cash_tolerance": dict(TOLERANCIA)}
    )


def _post_data(**over):
    data = {
        "ref": "t-tol", "label": "Caixa 1 renomeado", "channel_ref": "pdv", "location_ref": "",
        "is_active": "on", "station_mode": "attended",
        "cash_tolerance_percent": "50", "cash_tolerance_min": "0", "cash_tolerance_max": "999",
    }
    data.update(over)
    return data


def _form_for(user, terminal):
    request = RequestFactory().get("/")
    request.user = user
    return admin.site._registry[Terminal].get_form(request, terminal, change=True)


def test_gerente_salva_o_terminal_sem_mudar_a_tolerancia(gerente, terminal):
    form = _form_for(gerente, terminal)(data=_post_data(), instance=terminal)

    for name in ("cash_tolerance_percent", "cash_tolerance_min", "cash_tolerance_max"):
        assert form.fields[name].disabled, name
    assert form.is_valid(), form.errors
    saved = form.save()

    saved.refresh_from_db()
    assert saved.label == "Caixa 1 renomeado"
    assert saved.metadata["cash_tolerance"] == TOLERANCIA


def test_gerente_nao_cria_tolerancia_onde_nao_havia(gerente):
    terminal = Terminal.objects.create(ref="t-tol", label="Caixa 1", channel_ref="pdv")
    form = _form_for(gerente, terminal)(data=_post_data(), instance=terminal)
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()
    assert "cash_tolerance" not in saved.metadata


def test_dono_muda_a_tolerancia(dono, terminal):
    form = _form_for(dono, terminal)(data=_post_data(), instance=terminal)

    assert not form.fields["cash_tolerance_percent"].disabled
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()
    assert saved.metadata["cash_tolerance"] == {"percent": "50", "min_q": 0, "max_q": 99900}


def test_superusuario_muda_a_tolerancia(terminal):
    admin_user = User.objects.create_superuser("super-tolerancia", "s@test.com", "pw")
    form = _form_for(admin_user, terminal)(data=_post_data(), instance=terminal)
    assert form.is_valid(), form.errors
    saved = form.save()
    saved.refresh_from_db()
    assert saved.metadata["cash_tolerance"]["max_q"] == 99900


def test_tela_da_gerente_mostra_a_tolerancia_desabilitada(client, gerente, terminal):
    client.force_login(gerente)
    resp = client.get(reverse("admin:cashman_terminal_change", args=[terminal.pk]))

    assert resp.status_code == 200
    form = resp.context["adminform"].form
    assert form.fields["cash_tolerance_max"].disabled
    assert form["cash_tolerance_max"].value() == 15
    assert "Só o Dono altera a tolerância do caixa." in resp.content.decode()


def test_tela_do_dono_deixa_editar(client, dono, terminal):
    client.force_login(dono)
    resp = client.get(reverse("admin:cashman_terminal_change", args=[terminal.pk]))

    assert resp.status_code == 200
    assert not resp.context["adminform"].form.fields["cash_tolerance_max"].disabled
    assert "Só o Dono altera" not in resp.content.decode()
