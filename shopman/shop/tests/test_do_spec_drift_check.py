"""O drift-check enxerga domínio e ingress, e sabe o que é diferença de propósito.

O script nasceu (PR #546) olhando só env, e por isso deu "OK" enquanto o
arquivo trazia um domínio **morto** como PRIMARY e deixava de fora um domínio
**vivo**. `doctl apps update --spec` não faz merge em nenhuma seção: domínio e
regra de ingress somem com o mesmo silêncio que uma env.

O outro lado é o ruído. Duas chaves existem no arquivo e não no vivo de
propósito — `FOCUS_NFE_ENVIRONMENT` e `SENTRY_DSN` —, e um relatório que nunca
fecha limpo deixa de ser lido. Elas são **declaradas** como esperadas, com a
razão junto; o que não está declarado continua acusando.

⚠️ A allowlist de "só no arquivo" só vale para o lado "nasceriam". Na direção
que apaga (existe no vivo, não no arquivo) a declaração é outra, por chave, e
este arquivo prova que uma não cobre a outra.

Terceiro caso: a chave existe dos dois lados com valores diferentes de
propósito (a publicação pública é armada no painel; o arquivo nunca pré-arma).
A declaração prende os DOIS valores: qualquer outro par continua acusando.

O script vive fora da árvore do pacote, então é carregado por caminho.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_do_spec_drift.py"
_spec = importlib.util.spec_from_file_location("check_do_spec_drift", _SCRIPT)
drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drift)


def _env(key: str, value: str | None = None, *, secret: bool = False) -> dict:
    entry: dict = {"key": key, "scope": "RUN_TIME", "type": "SECRET" if secret else "GENERAL"}
    if value is not None:
        entry["value"] = value
    return entry


def _rule(component: str, host: str | None = None) -> dict:
    match: dict = {"path": {"prefix": "/"}}
    if host:
        match["authority"] = {"exact": host}
    return {"component": {"name": component}, "match": match}


# ---------------------------------------------------------------------------
# Diferença declarada como esperada
# ---------------------------------------------------------------------------


def test_expected_only_versioned_key_is_not_drift():
    problems, expected = drift.compare(
        {},
        {"FOCUS_NFE_ENVIRONMENT": _env("FOCUS_NFE_ENVIRONMENT", "homologacao")},
        label="envs de app",
        expected_only_versioned=drift.EXPECTED_ONLY_VERSIONED,
    )
    assert problems == []
    assert len(expected) == 1
    assert "FOCUS_NFE_ENVIRONMENT" in expected[0]
    # A razão viaja junto com a linha: quem confere não precisa abrir o script.
    assert "homologacao" in expected[0]


def test_undeclared_only_versioned_key_still_reports():
    problems, expected = drift.compare(
        {},
        {"NOVA_ENV": _env("NOVA_ENV", "x")},
        label="envs de app",
        expected_only_versioned=drift.EXPECTED_ONLY_VERSIONED,
    )
    assert expected == []
    assert any("NOVA_ENV" in line for line in problems)


def test_allowlist_never_covers_the_direction_that_deletes():
    """A mesma chave, do lado do vivo, continua sendo SUMIRIA."""
    problems, expected = drift.compare(
        {"SENTRY_DSN": _env("SENTRY_DSN", secret=True)},
        {},
        label="envs de app",
        expected_only_versioned=drift.EXPECTED_ONLY_VERSIONED,
    )
    assert expected == []
    assert any("SUMIRIAM" in line for line in problems)
    assert any("SENTRY_DSN" in line for line in problems)


# ---------------------------------------------------------------------------
# Divergência de valor declarada, e remoção declarada
# ---------------------------------------------------------------------------


def _compare_app_envs(live: dict, versioned: dict):
    return drift.compare(
        live,
        versioned,
        label="envs de app",
        expected_only_versioned=drift.EXPECTED_ONLY_VERSIONED,
        expected_only_live=drift.EXPECTED_ONLY_LIVE,
        expected_value_divergence=drift.EXPECTED_VALUE_DIVERGENCE,
    )


@pytest.mark.parametrize(
    "key",
    [
        "SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED",
        "SHOPMAN_MARKETING_FACEBOOK_PUBLICATION_ENABLED",
        "SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED",
    ],
)
def test_publication_armed_in_the_panel_is_not_drift(key):
    problems, expected = _compare_app_envs({key: _env(key, "true")}, {key: _env(key, "false")})
    assert problems == []
    assert len(expected) == 1
    assert key in expected[0]
    assert "ARMADA NO PAINEL" in expected[0]


def test_undeclared_value_divergence_still_reports():
    """Sem esta prova, a declaração nova viraria um jeito de calar drift."""
    problems, expected = _compare_app_envs(
        {"SHOPMAN_MARKETING_MEDIA_HOSTS": _env("SHOPMAN_MARKETING_MEDIA_HOSTS", "a.example")},
        {"SHOPMAN_MARKETING_MEDIA_HOSTS": _env("SHOPMAN_MARKETING_MEDIA_HOSTS", "b.example")},
    )
    assert expected == []
    assert any("SHOPMAN_MARKETING_MEDIA_HOSTS" in line and "`value` diverge" in line for line in problems)


@pytest.mark.parametrize(
    ("live_value", "versioned_value"),
    [
        ("false", "true"),  # o arquivo passou a pré-armar: é o que a guarda proíbe
        ("yes", "false"),  # o vivo mudou para um valor que ninguém declarou
    ],
)
def test_declared_key_with_another_value_pair_still_reports(live_value, versioned_value):
    key = "SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED"
    problems, expected = _compare_app_envs(
        {key: _env(key, live_value)}, {key: _env(key, versioned_value)}
    )
    assert expected == []
    assert any(key in line and "`value` diverge" in line for line in problems)


def test_declared_value_divergence_does_not_hide_scope_divergence():
    key = "SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED"
    live_entry = _env(key, "true")
    live_entry["scope"] = "RUN_AND_BUILD_TIME"
    problems, _ = _compare_app_envs({key: live_entry}, {key: _env(key, "false")})
    assert any(key in line and "`scope` diverge" in line for line in problems)


def test_declared_removal_from_the_live_app_is_not_drift():
    key = "FLAG_QUE_SAIU"
    problems, expected = drift.compare(
        {key: _env(key, "true")},
        {},
        label="envs de app",
        expected_only_live={key: "saiu do arquivo; nenhum código lê"},
    )
    assert problems == []
    assert len(expected) == 1
    assert key in expected[0]
    assert "nenhum código lê" in expected[0]


def test_ghost_flag_is_no_longer_declared_after_leaving_the_live_app():
    """Removida do vivo em 30/09/2026; se voltar ao painel, tem de acusar."""
    key = "SHOPMAN_REQUIRE_ACTIVE_OPERATOR"
    problems, expected = _compare_app_envs({key: _env(key, "true")}, {})
    assert expected == []
    assert any("SUMIRIAM" in line for line in problems)


def test_undeclared_key_only_in_the_live_app_still_deletes():
    problems, expected = _compare_app_envs({"EMAIL_HOST": _env("EMAIL_HOST", "smtp.x")}, {})
    assert expected == []
    assert any("SUMIRIAM" in line for line in problems)
    assert any("EMAIL_HOST" in line for line in problems)


# ---------------------------------------------------------------------------
# Valor de segredo
# ---------------------------------------------------------------------------


def test_secret_value_is_never_compared_nor_printed():
    problems, _ = drift.compare(
        {"EMAIL_HOST_PASSWORD": _env("EMAIL_HOST_PASSWORD", "EV[1:cifrado:blob]", secret=True)},
        {"EMAIL_HOST_PASSWORD": _env("EMAIL_HOST_PASSWORD", secret=True)},
        label="envs de app",
    )
    assert problems == []


# ---------------------------------------------------------------------------
# Domínios
# ---------------------------------------------------------------------------


def test_domain_only_in_the_live_app_is_reported_as_deleting():
    live = {"domains": [{"domain": "backup.boulangerie.com.br", "type": "ALIAS", "zone": "b"}]}
    problems = drift.compare_plain(
        drift.domain_index(live), drift.domain_index({}), label="domínios", unit="hostnames"
    )
    assert any("SUMIRIAM" in line for line in problems)
    assert any("backup.boulangerie.com.br" in line for line in problems)


def test_dead_domain_only_in_the_file_is_reported_as_being_born():
    versioned = {"domains": [{"domain": "alpha.nelsonboulangerie.com.br", "type": "PRIMARY"}]}
    problems = drift.compare_plain(
        drift.domain_index({}),
        drift.domain_index(versioned),
        label="domínios",
        unit="hostnames",
    )
    assert any("nasceriam" in line for line in problems)
    assert any("alpha.nelsonboulangerie.com.br" in line for line in problems)


def test_primary_moving_between_hosts_is_a_divergence():
    live = {"domains": [{"domain": "menu.x.br", "type": "PRIMARY", "zone": "x.br"}]}
    versioned = {"domains": [{"domain": "menu.x.br", "type": "ALIAS", "zone": "x.br"}]}
    problems = drift.compare_plain(
        drift.domain_index(live),
        drift.domain_index(versioned),
        label="domínios",
        unit="hostnames",
    )
    assert any("PRIMARY" in line and "ALIAS" in line for line in problems)


# ---------------------------------------------------------------------------
# Ingress
# ---------------------------------------------------------------------------


def test_ingress_rule_serving_another_component_is_a_divergence():
    live = {"ingress": {"rules": [_rule("web", "backup.b.br")]}}
    versioned = {"ingress": {"rules": [_rule("storefront-nuxt", "backup.b.br")]}}
    problems = drift.compare_plain(
        drift.ingress_index(live), drift.ingress_index(versioned), label="ingress", unit="regras"
    )
    assert any("web" in line and "storefront-nuxt" in line for line in problems)


def test_ingress_is_compared_as_a_set_not_as_an_ordered_list():
    """O painel acrescenta regra no fim; o arquivo agrupa por leitura.

    Se a ordem contasse, todo ciclo de conferência acusaria uma diferença que
    não muda roteamento nenhum — e o relatório perderia a autoridade que só tem
    enquanto não mente.
    """
    rules = [_rule("web", "api.b.br"), _rule("pos-nuxt", "pdv.b.br"), _rule("storefront-nuxt")]
    live = {"ingress": {"rules": rules}}
    versioned = {"ingress": {"rules": list(reversed(rules))}}
    assert (
        drift.compare_plain(
            drift.ingress_index(live),
            drift.ingress_index(versioned),
            label="ingress",
            unit="regras",
        )
        == []
    )


def test_missing_catch_all_rule_is_reported():
    live = {"ingress": {"rules": [_rule("storefront-nuxt")]}}
    problems = drift.compare_plain(
        drift.ingress_index(live), drift.ingress_index({}), label="ingress", unit="regras"
    )
    assert any("<catch-all>" in line for line in problems)


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("section", ["domains", "ingress"])
def test_main_fails_when_only_a_non_env_section_diverges(tmp_path, capsys, section):
    """Antes, drift fora de `envs` saía com 0 — o update parecia liberado."""
    import yaml

    base = {
        "name": "app",
        "envs": [_env("A", "1")],
        "domains": [{"domain": "menu.x.br", "type": "PRIMARY", "zone": "x.br"}],
        "ingress": {"rules": [_rule("storefront-nuxt", "menu.x.br")]},
    }
    versioned = {**base, section: [] if section == "domains" else {"rules": []}}

    live_path = tmp_path / "vivo.yaml"
    spec_path = tmp_path / "versionado.yaml"
    live_path.write_text(yaml.safe_dump(base), encoding="utf-8")
    spec_path.write_text(yaml.safe_dump(versioned), encoding="utf-8")

    code = drift.main(["--spec", str(spec_path), "--live-spec", str(live_path)])
    assert code == 1
    assert "SUMIRIAM" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Bancos anexados: o incidente de 29-30/09/2026
# ---------------------------------------------------------------------------

#: O bloco do arquivo versionado, idêntico ao `.do/app.alpha-subdomains.yaml`.
_DATABASES_FULL = [
    {
        "cluster_name": "shopman-staging-postgres",
        "db_name": "shopman",
        "db_user": "shopman",
        "engine": "PG",
        "name": "postgres",
        "production": True,
        "version": "16",
    },
    {
        "cluster_name": "shopman-staging-cache",
        "engine": "VALKEY",
        "name": "cache",
        "production": True,
        "version": "8",
    },
]

#: O que o `apps update` do deployment ded45b84 deixou no vivo (29/09 21:47 UTC).
_DATABASES_MUTILATED = [{"name": "postgres"}, {"name": "cache"}]


def test_real_case_mutilated_databases_block_fails_naming_postgres(tmp_path, capsys):
    """Reconstituição do incidente: o vivo com `databases` reduzido a `name`.

    Por 21 horas todo deploy morreu em `Creating database` com InternalError,
    e o drift-check, que não olhava `databases`, teria dito OK para o bloco.
    """
    import yaml

    base = {"name": "app", "envs": [_env("A", "1")]}
    live_path = tmp_path / "vivo.yaml"
    spec_path = tmp_path / "versionado.yaml"
    live_path.write_text(yaml.safe_dump({**base, "databases": _DATABASES_MUTILATED}), encoding="utf-8")
    spec_path.write_text(yaml.safe_dump({**base, "databases": _DATABASES_FULL}), encoding="utf-8")

    code = drift.main(["--spec", str(spec_path), "--live-spec", str(live_path)])
    out = capsys.readouterr().out

    assert code == 1
    assert "[FAIL]" in out
    assert "databases MUTILADO" in out
    postgres_lines = [line for line in out.splitlines() if "databases postgres" in line]
    assert postgres_lines, out
    assert any("cluster_name='shopman-staging-postgres'" in line for line in postgres_lines)
    assert any("db_name='shopman'" in line for line in postgres_lines)


def test_healthy_databases_block_is_clean():
    live = drift.database_index({"databases": _DATABASES_FULL})
    assert drift.compare_records(live, dict(live), label="databases", unit="bancos") == []
    assert drift.mutilated_databases(live, live) == []


def test_cache_without_db_name_is_not_drift():
    """Compara contra o versionado, não contra um conjunto fixo de campos."""
    index = drift.database_index({"databases": _DATABASES_FULL})
    assert "db_name" not in index["cache"]
    assert drift.compare_records(index, dict(index), label="databases", unit="bancos") == []


def test_single_database_field_lost_in_the_live_app_fails():
    live_block = [dict(_DATABASES_FULL[0]), dict(_DATABASES_FULL[1])]
    del live_block[0]["cluster_name"]
    problems = drift.compare_records(
        drift.database_index({"databases": live_block}),
        drift.database_index({"databases": _DATABASES_FULL}),
        label="databases",
        unit="bancos",
    )
    assert any("postgres" in line and "cluster_name" in line for line in problems)


def test_database_only_in_the_live_app_is_reported_as_deleting():
    problems = drift.compare_records(
        drift.database_index({"databases": _DATABASES_FULL}),
        drift.database_index({"databases": _DATABASES_FULL[:1]}),
        label="databases",
        unit="bancos",
    )
    assert any("SUMIRIAM" in line for line in problems)
    assert any(line.strip() == "cache" for line in problems)


def test_blind_token_refuses_instead_of_reporting_false_drift(tmp_path, capsys, monkeypatch):
    """Token sem escopo de database lê o bloco mutilado num app sadio.

    Medido em 30/09: o contexto de deploy devolve `databases` só com `name`
    mesmo depois da correção. O check recusa a leitura (2) em vez de acusar.
    """
    import yaml

    spec_path = tmp_path / "versionado.yaml"
    spec_path.write_text(
        yaml.safe_dump({"name": "app", "databases": _DATABASES_FULL}), encoding="utf-8"
    )
    monkeypatch.setattr(drift, "app_id_for", lambda name, context=None: "uuid")
    monkeypatch.setattr(
        drift,
        "fetch_live_spec",
        lambda app_id, context=None: {"name": "app", "databases": _DATABASES_MUTILATED},
    )
    monkeypatch.setattr(drift, "token_reads_databases", lambda context=None: False)

    assert drift.main(["--spec", str(spec_path)]) == 2
    assert "leitura cega" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Componentes: imagem e dimensionamento
# ---------------------------------------------------------------------------


def _component(name: str, tag: str = "web", **extra) -> dict:
    return {
        "name": name,
        "instance_count": 1,
        "instance_size_slug": "apps-s-1vcpu-1gb",
        "image": {
            "registry_type": "DOCR",
            "repository": "shopman",
            "tag": tag,
            "deploy_on_push": {"enabled": True},
            **extra,
        },
    }


def test_registry_filled_by_the_platform_is_not_drift():
    live = {"services": [_component("web", registry="nelsonboulangerie")]}
    versioned = {"services": [_component("web")]}
    assert (
        drift.compare_records(
            drift.component_index(live), drift.component_index(versioned), label="c", unit="c"
        )
        == []
    )


def test_image_tag_divergence_is_reported():
    problems = drift.compare_records(
        drift.component_index({"workers": [_component("directive-worker", tag="web-old")]}),
        drift.component_index({"workers": [_component("directive-worker", tag="web")]}),
        label="componente",
        unit="componentes",
    )
    assert any("workers/directive-worker" in line and "image.tag" in line for line in problems)


@pytest.mark.parametrize("field", ["instance_count", "instance_size_slug"])
def test_sizing_lost_in_the_live_app_fails(field):
    live_component = _component("web")
    del live_component[field]
    problems = drift.compare_records(
        drift.component_index({"services": [live_component]}),
        drift.component_index({"services": [_component("web")]}),
        label="componente",
        unit="componentes",
    )
    assert any("services/web" in line and field in line for line in problems)


def test_component_only_in_the_live_app_is_reported_as_deleting():
    problems = drift.compare_records(
        drift.component_index({"workers": [_component("ifood-poll-worker")]}),
        drift.component_index({}),
        label="componente",
        unit="componentes",
    )
    assert any("SUMIRIAM" in line for line in problems)
    assert any("workers/ifood-poll-worker" in line for line in problems)


def test_deploy_on_push_turned_off_is_a_divergence():
    live_component = _component("web")
    live_component["image"]["deploy_on_push"] = {"enabled": False}
    problems = drift.compare_records(
        drift.component_index({"services": [live_component]}),
        drift.component_index({"services": [_component("web")]}),
        label="componente",
        unit="componentes",
    )
    assert any("deploy_on_push" in line for line in problems)
