"""O drift-check enxerga domínio e ingress, e sabe o que é diferença de propósito.

O script nasceu (PR #546) olhando só env, e por isso deu "OK" enquanto o
arquivo trazia um domínio **morto** como PRIMARY e deixava de fora um domínio
**vivo**. `doctl apps update --spec` não faz merge em nenhuma seção: domínio e
regra de ingress somem com o mesmo silêncio que uma env.

O outro lado é o ruído. Duas chaves existem no arquivo e não no vivo de
propósito — `FOCUS_NFE_ENVIRONMENT` e `SENTRY_DSN` —, e um relatório que nunca
fecha limpo deixa de ser lido. Elas são **declaradas** como esperadas, com a
razão junto; o que não está declarado continua acusando.

⚠️ A allowlist só vale para o lado "nasceriam". Na direção que apaga
(existe no vivo, não no arquivo) não há allowlist nenhuma, e este arquivo
prova isso.

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
