"""``setup_groups`` (release) aplica as personas do descritor configurado, e só elas."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import CommandError

from config.instance_descriptors import load_descriptor

ROOT = Path(__file__).resolve().parents[2]
NELSON = ROOT / "config/instances/nelson.json"
COUNTER = ROOT / "config/instances/counter-minimal.json"

pytestmark = pytest.mark.django_db


def _run() -> str:
    out = StringIO()
    call_command("setup_groups", stdout=out)
    return out.getvalue()


def _grants(name: str) -> set[str]:
    return {
        f"{app_label}.{codename}"
        for app_label, codename in Group.objects.get(name=name).permissions.values_list(
            "content_type__app_label", "codename"
        )
    }


def test_release_da_nelson_aplica_exatamente_as_personas_do_descritor(settings):
    settings.SHOPMAN_INSTANCE_DESCRIPTOR = str(NELSON)

    _run()

    declared = {p["name"]: set(p["permissions"]) for p in load_descriptor(NELSON)["bootstrap"]["rbac_personas"]}
    assert set(Group.objects.values_list("name", flat=True)) == set(declared)
    for name, permissions in declared.items():
        assert _grants(name) == permissions, name


def test_release_de_outra_instancia_nao_instala_os_grupos_da_nelson(settings):
    settings.SHOPMAN_INSTANCE_DESCRIPTOR = str(COUNTER)

    out = _run()

    assert list(Group.objects.values_list("name", flat=True)) == ["Counter operator"]
    assert _grants("Counter operator") == {"cashman.operate_pos"}
    assert "Instância: counter-minimal" in out


def test_concessao_a_mao_num_grupo_declarado_sai_e_o_log_diz_qual(settings):
    settings.SHOPMAN_INSTANCE_DESCRIPTOR = str(COUNTER)
    _run()
    extra = Permission.objects.get(content_type__app_label="cashman", codename="audit_shift")
    Group.objects.get(name="Counter operator").permissions.add(extra)
    custom = Group.objects.create(name="Supervisor")
    custom.permissions.add(extra)

    out = _run()

    assert _grants("Counter operator") == {"cashman.operate_pos"}
    assert "revogadas: cashman.audit_shift" in out
    # Grupo que o descritor não declara não é tocado.
    assert _grants("Supervisor") == {"cashman.audit_shift"}


def test_sem_descritor_o_release_falha_gritando(settings, tmp_path):
    settings.SHOPMAN_INSTANCE_DESCRIPTOR = str(tmp_path / "nao-existe.json")

    with pytest.raises(CommandError, match="SHOPMAN_INSTANCE_DESCRIPTOR"):
        _run()
    assert not Group.objects.exists()
