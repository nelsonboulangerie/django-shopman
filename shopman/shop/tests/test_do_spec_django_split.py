"""O Django em dois services: `web-operator` e `web-storefront`, mesma imagem.

O que esta trava garante nos dois specs de `.do/`:

- não sobra service `web`, e os dois novos são o MESMO programa (imagem ou
  build, comando, porta, health, chaves de env). Divergir aqui é ter dois
  Djangos diferentes atrás do mesmo `api.`;
- o operador roda em instância DEDICADA, a loja em compartilhada;
- o ingress do `api.` manda `/api/v1/backstage` ao operador ANTES de mandar
  `/api/v1` à loja, e o resto do host (Admin, `/events/`, webhooks) ao operador;
- toda regra com prefixo diferente de `/` que entrega a um componente preserva o
  prefixo (`preserve_path_prefix: true`);
- todo componente citado no ingress existe.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]
SPECS = {
    "app.alpha-subdomains.yaml": "boulangerie.com.br",
    "app.subdomains.yaml": "STORE_DOMAIN",
}
DJANGO = ("web-operator", "web-storefront")


def _spec(name: str) -> dict:
    return yaml.safe_load((ROOT / ".do" / name).read_text(encoding="utf-8"))


def _services(spec: dict) -> dict[str, dict]:
    return {service["name"]: service for service in spec["services"]}


@pytest.mark.parametrize("spec_name", SPECS)
def test_django_runs_as_two_services_of_the_same_program(spec_name):
    services = _services(_spec(spec_name))
    assert "web" not in services
    operator, storefront = (services[name] for name in DJANGO)
    for key in ("image", "git", "dockerfile_path", "source_dir", "run_command", "http_port",
                "health_check", "liveness_health_check"):
        assert operator.get(key) == storefront.get(key), key

    def env_shape(service):
        return {(e["key"], e["scope"], e["type"], e.get("value")) for e in service["envs"]}

    assert env_shape(operator) == env_shape(storefront)
    for service in (operator, storefront):
        for entry in service["envs"]:
            if entry["type"] == "SECRET":
                assert "value" not in entry, entry["key"]
    assert "daphne" in operator["run_command"]
    assert "--access-log=/dev/null" in operator["run_command"]


@pytest.mark.parametrize("spec_name", SPECS)
def test_operator_is_dedicated_and_storefront_is_shared(spec_name):
    services = _services(_spec(spec_name))
    assert services["web-operator"]["instance_size_slug"] == "apps-d-1vcpu-2gb"
    assert services["web-storefront"]["instance_size_slug"].startswith("apps-s-")
    for name in DJANGO:
        rules = {alert["rule"] for alert in services[name].get("alerts") or []}
        assert {"CPU_UTILIZATION", "MEM_UTILIZATION", "RESTART_COUNT"} <= rules, name


def _rules_for(spec: dict, host: str) -> list[tuple[str, str]]:
    out = []
    for rule in spec["ingress"]["rules"]:
        authority = (rule.get("match") or {}).get("authority") or {}
        if authority.get("exact") == host and rule.get("component"):
            out.append((rule["match"]["path"]["prefix"], rule["component"]["name"]))
    return out


@pytest.mark.parametrize("spec_name,domain", SPECS.items())
def test_api_host_routes_by_path_most_specific_first(spec_name, domain):
    spec = _spec(spec_name)
    assert _rules_for(spec, f"api.{domain}") == [
        ("/api/v1/backstage", "web-operator"),
        ("/api/v1", "web-storefront"),
        ("/", "web-operator"),
    ]
    assert _rules_for(spec, f"admin.{domain}") == [("/", "web-operator")]
    assert _rules_for(spec, f"backup.{domain}") == [("/", "web-operator")]


@pytest.mark.parametrize("spec_name", SPECS)
def test_every_ingress_component_exists(spec_name):
    spec = _spec(spec_name)
    names = set(_services(spec))
    for rule in spec["ingress"]["rules"]:
        component = (rule.get("component") or {}).get("name")
        if component:
            assert component in names, component


@pytest.mark.parametrize("spec_name", SPECS)
def test_prefixed_component_rules_preserve_the_prefix(spec_name):
    """A DO CORTA o prefixo da regra antes de entregar ao componente, por padrão.

    Em 10/10 o split subiu sem `preserve_path_prefix` e o Django recebeu
    `/storefront/...` no lugar de `/api/v1/storefront/...`: a API inteira deu 404
    no alpha por ~20 min. Quem quiser cortar o prefixo declara `rewrite`.
    """
    for rule in _spec(spec_name)["ingress"]["rules"]:
        component = rule.get("component")
        prefix = rule["match"]["path"]["prefix"]
        if not component or prefix == "/" or "rewrite" in component:
            continue
        assert component.get("preserve_path_prefix") is True, (prefix, component["name"])
        # A DO normaliza o prefixo sem barra final; o arquivo fala como o vivo.
        assert not prefix.endswith("/"), prefix


def test_storefront_api_routes_live_under_api_v1_and_backstage_is_separate():
    """O corte por path só vale se as rotas moram onde o ingress acha que moram."""
    from django.urls import reverse

    assert reverse("api-tracking", args=["X"]).startswith("/api/v1/")
    assert not reverse("api-tracking", args=["X"]).startswith("/api/v1/backstage/")
    assert reverse("backstage:events", args=["kds"]).startswith("/events/")
    assert reverse("webhooks:efi-pix-webhook").startswith("/api/webhooks/")
