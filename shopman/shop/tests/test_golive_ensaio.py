"""Ensaio geral da virada: o spec do dia D, o reapontar e o env local, fora do vivo.

``scripts/golive_ensaio.py`` escreve arquivos que NUNCA vão para o app vivo:
o spec como fica depois da gravação única do dono, o spec com o banco
reapontado para o cluster restaurado e o env de um componente com segredos
sintéticos. Estes testes prendem as três promessas que tornam o ensaio
honesto: o "depois" fecha o delta inteiro (a mesma tabela do dia D), o
reapontar troca uma linha só, e nenhum valor de segredo do spec sai do arquivo.
"""

from __future__ import annotations

import copy
import re
import stat
from pathlib import Path

import pytest
import yaml

from scripts import golive_ensaio as ensaio
from scripts import golive_spec_delta as delta
from shopman.shop.tests.test_golive_spec_delta import _env, _today

_ROOT = Path(__file__).resolve().parents[3]
_RUNBOOK = _ROOT / "docs" / "runbooks" / "ensaio-geral-da-virada.md"


def _with_databases(spec: dict) -> dict:
    spec["databases"] = [
        {"cluster_name": "shopman-staging-postgres", "db_name": "shopman", "engine": "PG", "name": "postgres"},
        {"cluster_name": "shopman-staging-cache", "engine": "VALKEY", "name": "cache"},
    ]
    return spec


# ── depois ───────────────────────────────────────────────────────────────────


def test_depois_fecha_o_delta_inteiro_contra_o_spec_de_antes():
    antes = _today()
    depois, changes = ensaio.apply_delta(antes)

    findings = delta.evaluate(depois, baseline_spec=antes)
    assert {f.row.key: f.status for f in findings if f.status != "ok"} == {}
    _, code = delta.render(findings, etapa="dia-d", has_baseline=True)
    assert code == 0
    assert "SHOPMAN_ENVIRONMENT = production" in changes
    assert "apagar SHOPMAN_EXPOSE_MOCK_CAPTURE" in changes


def test_depois_nao_mexe_no_antes():
    antes = _today()
    frozen = copy.deepcopy(antes)

    ensaio.apply_delta(antes)

    assert antes == frozen


def test_segredo_trocado_vira_marcador_secreto_e_o_resto_fica_intacto():
    antes = _today()
    depois, _ = ensaio.apply_delta(antes)
    envs = {entry["key"]: entry for entry in depois["envs"]}

    assert envs["STRIPE_SECRET_KEY"]["value"] == f"{ensaio.MARK}-STRIPE_SECRET_KEY"
    assert envs["STRIPE_SECRET_KEY"]["type"] == "SECRET"
    assert envs["STRIPE_PUBLISHABLE_KEY"]["value"].startswith("pk_live_")
    # Segredo que o dia D não troca segue com o cifrado de antes.
    assert envs["DJANGO_SECRET_KEY"]["value"] == "EV[1:antes-DJANGO_SECRET_KEY]"


def test_override_de_componente_tambem_vira():
    antes = _today()
    for component in antes["workers"]:
        component["envs"].append(_env("SHOPMAN_ENVIRONMENT", "staging"))

    depois, _ = ensaio.apply_delta(antes)

    findings = {f.row.key: f for f in delta.evaluate(depois, baseline_spec=antes)}
    assert findings["SHOPMAN_ENVIRONMENT"].status == "ok"


def test_chave_que_falta_no_antes_nao_e_inventada():
    antes = _today()
    antes["envs"] = [entry for entry in antes["envs"] if entry["key"] != "COMTELE_ROUTE"]

    depois, changes = ensaio.apply_delta(antes)

    assert "COMTELE_ROUTE: FALTA no spec (o ensaio não inventa)" in changes
    status = {f.row.key: f.status for f in delta.evaluate(depois, baseline_spec=antes)}
    assert status["COMTELE_ROUTE"] == "virar"


def test_spec_escrito_poe_aspas_no_que_a_do_leria_como_numero():
    spec = _today()
    spec["envs"].append(_env("FOCUS_NFE_CNPJ_EMITENTE", "02119381000158"))

    text = ensaio.dump_spec(spec)

    assert text.startswith("# ENSAIO GERAL DA VIRADA")
    assert "'02119381000158'" in text
    assert "value: '8'" in text
    assert "value: 'true'" in text
    assert yaml.safe_load(text) == spec


# ── reapontar ────────────────────────────────────────────────────────────────


def _flat(node, prefix=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _flat(value, f"{prefix}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _flat(value, f"{prefix}[{index}]")
    else:
        yield prefix, node


def test_reapontar_troca_uma_linha_so():
    antes = _with_databases(_today())

    novo, old = ensaio.repoint(antes, cluster="shopman-staging-postgres-oct-20-backup")

    assert old == "shopman-staging-postgres"
    before, after = dict(_flat(antes)), dict(_flat(novo))
    assert [key for key in before.keys() | after.keys() if before.get(key) != after.get(key)] == [
        ".databases[0].cluster_name"
    ]


@pytest.mark.parametrize(
    ("cluster", "database", "message"),
    [
        ("shopman-staging-postgres", "postgres", "já aponta"),
        ("x", "nao-existe", "não tem banco"),
        ("  ", "postgres", "vazio"),
    ],
)
def test_reapontar_recusa_o_que_nao_e_troca(cluster, database, message):
    with pytest.raises(ensaio.EnsaioError, match=message):
        ensaio.repoint(_with_databases(_today()), cluster=cluster, database=database)


# ── env ──────────────────────────────────────────────────────────────────────


def _build(spec: dict, **kwargs):
    defaults = {
        "component": "release",
        "database_url": "postgres://shopman@127.0.0.1:37201/shopman",
        "redis_url": "redis://127.0.0.1:37202/0",
        "efi_cert_path": "/tmp/efi-sintetico.pem",
    }
    return ensaio.build_env(spec, **{**defaults, **kwargs})


def test_env_nunca_carrega_valor_de_segredo_do_spec():
    depois, _ = ensaio.apply_delta(_today())

    values, report = _build(depois)
    text = ensaio.render_env(values, report, component="release")

    assert "EV[" not in text
    assert ensaio.MARK not in text
    assert values["STRIPE_SECRET_KEY"].startswith("sk_live_ensaio_")
    assert values["STRIPE_PUBLISHABLE_KEY"].startswith("pk_live_")
    assert values["DJANGO_SECRET_KEY"].startswith("ensaio-sintetico-")
    assert values["SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY"].startswith("ensaio-sintetico-")
    assert "EFI_CERTIFICATE_PEM_BASE64" not in values
    assert values["EFI_CERTIFICATE_PATH"] == "/tmp/efi-sintetico.pem"


def test_env_do_spec_de_antes_continua_em_modo_teste():
    values, _ = _build(_today())

    assert values["STRIPE_SECRET_KEY"].startswith("sk_test_ensaio_")
    assert values["SHOPMAN_ENVIRONMENT"] == "staging"


def test_env_troca_as_referencias_do_app_platform_pelas_do_ensaio():
    values, report = _build(_today(), extra_hosts=("127.0.0.1",))

    assert values["DATABASE_URL"] == "postgres://shopman@127.0.0.1:37201/shopman"
    assert values["REDIS_URL"] == "redis://127.0.0.1:37202/0"
    assert sorted(report["referencia"]) == ["DATABASE_URL", "REDIS_URL"]
    assert values["DJANGO_ALLOWED_HOSTS"].endswith(",127.0.0.1")


def test_env_exige_certificado_sintetico_quando_o_spec_tem_o_da_efi():
    with pytest.raises(ensaio.EnsaioError, match="--efi-cert-path"):
        _build(_today(), efi_cert_path="")


def test_env_recusa_componente_que_nao_roda_django():
    with pytest.raises(ensaio.EnsaioError, match="storefront-nuxt"):
        _build(_today(), component="storefront-nuxt")


# ── CLI ──────────────────────────────────────────────────────────────────────


def _write_spec(path: Path, spec: dict) -> Path:
    path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return path


def test_cli_recusa_escrever_dentro_do_repositorio(tmp_path, capsys):
    antes = _write_spec(tmp_path / "antes.yaml", _today())

    code = ensaio.main(["depois", "--antes", str(antes), "--saida", str(_ROOT / "docs" / "depois.yaml")])

    assert code == 2
    assert "dentro do repositório" in capsys.readouterr().err
    assert not (_ROOT / "docs" / "depois.yaml").exists()


def test_cli_escreve_fora_do_repositorio_so_para_o_dono_do_arquivo(tmp_path):
    antes = _write_spec(tmp_path / "antes.yaml", _with_databases(_today()))
    depois = tmp_path / "depois.ensaio.yaml"
    env = tmp_path / "release.env"
    novo = tmp_path / "reapontado.ensaio.yaml"

    assert ensaio.main(["depois", "--antes", str(antes), "--saida", str(depois)]) == 0
    assert delta.main(["--live-spec", str(depois), "--baseline", str(antes)]) == 0
    assert ensaio.main(["reapontar", "--antes", str(antes), "--cluster", "drill", "--saida", str(novo)]) == 0
    assert (
        ensaio.main(
            [
                "env",
                "--spec",
                str(depois),
                "--database-url",
                "postgres://shopman@127.0.0.1:37201/shopman",
                "--redis-url",
                "redis://127.0.0.1:37202/0",
                "--efi-cert-path",
                str(tmp_path / "efi.pem"),
                "--host-extra",
                "127.0.0.1",
                "--saida",
                str(env),
            ]
        )
        == 0
    )
    for path in (depois, env, novo):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "export SHOPMAN_ENVIRONMENT=production" in env.read_text(encoding="utf-8")


# ── runbook ──────────────────────────────────────────────────────────────────


def test_runbook_cita_os_tres_subcomandos_e_a_porta_direta():
    text = _RUNBOOK.read_text(encoding="utf-8")

    for command in ("depois", "reapontar", "env"):
        assert re.search(rf'golive_ensaio\.py"? {command} ', text), command
    assert ":25060/" in text
    # O pool (25061) só aparece como proibição, nunca num comando.
    for line in text.splitlines():
        if "25061" in line:
            assert "nunca" in line.lower() or "não" in line.lower(), line
