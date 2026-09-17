"""Nuxt deploy config guardrails for the subdomain topology."""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
SURFACES = (
    "storefront-nuxt",
    "hub-nuxt",
    "pos-nuxt",
    "kds-nuxt",
    "orders-nuxt",
    "production-nuxt",
    "purchase-nuxt",
    "marketing-nuxt",
    "bi-nuxt",
)
NUXT_RUNTIMES = (*SURFACES, "operator-kit")


def _version_tuple(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")[:3]
    return int(major), int(minor), int(patch)


def test_operator_surfaces_default_to_subdomain_root_base_url():
    for surface in ("pos-nuxt", "kds-nuxt", "hub-nuxt"):
        source = (ROOT / "surfaces" / surface / "nuxt.config.ts").read_text()
        assert 'baseURL: process.env.NUXT_APP_BASE_URL || "/"' in source


def test_nuxt_lockfiles_use_security_patched_runtime():
    for surface in NUXT_RUNTIMES:
        lock = json.loads((ROOT / "surfaces" / surface / "package-lock.json").read_text())
        version = lock["packages"]["node_modules/nuxt"]["version"]
        assert _version_tuple(version) >= (4, 5, 1), f"{surface} pins vulnerable nuxt {version}"


def test_nuxt_ssr_runtime_imports_resolve_to_compatible_packages():
    for surface in NUXT_RUNTIMES:
        lock = json.loads((ROOT / "surfaces" / surface / "package-lock.json").read_text())
        packages = lock["packages"]
        vue_version = packages["node_modules/vue"]["version"]
        renderer_version = packages["node_modules/@vue/server-renderer"]["version"]
        nostics_version = packages["node_modules/nostics"]["version"]

        assert vue_version == renderer_version, f"{surface} mixes vue {vue_version} with renderer {renderer_version}"
        assert _version_tuple(vue_version) >= (3, 5, 41), f"{surface} pins SSR-incompatible vue {vue_version}"
        assert _version_tuple(nostics_version) >= (1, 2, 0), f"{surface} hoists SSR-incompatible nostics {nostics_version}"


def test_make_surfaces_includes_all_nuxt_apps():
    source = (ROOT / "Makefile").read_text()
    line = next(line for line in source.splitlines() if line.startswith("SURFACES :="))
    for surface in SURFACES:
        assert surface in line


OPERATOR_GROUPS_FILE = ROOT / "surfaces" / "operator-router" / "groups.json"
DEPLOY_SPECS = (
    ROOT / ".do" / "app.alpha-subdomains.yaml",
    ROOT / ".do" / "app.subdomains.yaml",
)


def _operator_groups() -> dict[str, list[dict]]:
    return {name: group["apps"] for name, group in json.loads(OPERATOR_GROUPS_FILE.read_text()).items()}


def _group_of(surface: str) -> str | None:
    for name, apps in _operator_groups().items():
        if any(app["surface"] == surface for app in apps):
            return name
    return None


def _env_map(service: dict) -> dict[str, str]:
    return {entry["key"]: str(entry.get("value") or "") for entry in service.get("envs") or []}


def test_operator_groups_cover_every_operator_surface_exactly_once():
    """Os dois grupos da ADR-030 somam os oito apps de operador — nem um a mais.

    `groups.json` é a lista que o launcher sobe, que o deploy-images.yml lê e que
    este teste confere contra `SURFACES`. App de operador novo que não entra num
    grupo não teria contêiner; app em dois grupos subiria duas vezes.
    """
    groups = _operator_groups()
    assert set(groups) == {"operator-floor", "operator-office"}
    members = [app["surface"] for apps in groups.values() for app in apps]
    assert sorted(members) == sorted(s for s in SURFACES if s != "storefront-nuxt")
    assert len(members) == len(set(members))
    assert [app["surface"] for app in groups["operator-floor"]] == [
        "pos-nuxt", "kds-nuxt", "orders-nuxt", "production-nuxt", "hub-nuxt",
    ]
    for apps in groups.values():
        for app in apps:
            assert app["id"] == app["surface"].removesuffix("-nuxt"), (
                f"{app['surface']}: o id (prefixo das envs) tem de ser a tag de sempre"
            )


def test_operator_group_dockerfile_builds_each_app_into_its_group():
    """Cada app tem estágio próprio e é copiado para o estágio do SEU grupo."""
    source = (ROOT / "surfaces" / "Dockerfile.operator-group").read_text()
    stages = {}
    current = None
    for line in source.splitlines():
        if line.startswith("FROM "):
            current = line.split(" AS ")[-1].strip() if " AS " in line else None
            stages[current] = []
        elif current:
            stages[current].append(line)
    assert "FROM ${OPERATOR_GROUP} AS group" in source
    for group, apps in _operator_groups().items():
        assert group in stages, f"Dockerfile sem estágio {group}"
        body = "\n".join(stages[group])
        assert f"ENV OPERATOR_GROUP={group}" in body
        for app in apps:
            assert app["id"] in stages, f"Dockerfile sem estágio de build de {app['surface']}"
            copy = f"COPY --from={app['id']} /repo/surfaces/{app['surface']}/.output ./apps/{app['surface']}/.output"
            assert copy in body, f"{app['surface']} não é copiado para {group}"
        others = [a for g, apps_ in _operator_groups().items() if g != group for a in apps_]
        for app in others:
            assert f"./apps/{app['surface']}/" not in body, f"{app['surface']} vazou para {group}"


def test_alpha_app_platform_spec_routes_all_nuxt_apps():
    """Cada superfície Nuxt é alcançável no spec e servida pela IMAGEM certa.

    Desde 26/08 o deploy é por imagem do DOCR (deploy-images.yml), não por
    buildpack com ``source_dir``: o push da tag móvel VIRA o deploy. Desde a
    ADR-030 os apps de operador não têm service próprio: o ingress do hostname
    aponta para o service do GRUPO (`operator-floor`/`operator-office`, tag de
    mesmo nome) e o `OPERATOR_HOSTS` daquele service entrega o hostname ao app.
    O storefront continua com service e tag próprios.
    """
    import yaml

    spec = yaml.safe_load((ROOT / ".do" / "app.alpha-subdomains.yaml").read_text())
    services = {svc["name"]: svc for svc in spec.get("services") or []}
    routes = {
        (rule.get("match") or {}).get("authority", {}).get("exact"): rule["component"]["name"]
        for rule in spec["ingress"]["rules"]
        # Regra de redirect (apex → www) não tem component.
        if (rule.get("match") or {}).get("authority") and rule.get("component")
    }

    def assert_image(name: str, tag: str) -> None:
        assert name in services, f"{name} sem service no spec do alpha"
        image = services[name].get("image") or {}
        assert image.get("registry_type") == "DOCR", f"{name} não deploya por imagem do DOCR"
        assert image.get("repository") == "shopman", f"{name} fora do repositório shopman"
        assert image.get("tag") == tag, f"{name} com tag {image.get('tag')!r}; o deploy-images.yml publica {tag!r}"
        assert (image.get("deploy_on_push") or {}).get("enabled") is True, (
            f"{name} sem deploy_on_push — o push do Actions não viraria deploy"
        )

    assert_image("storefront-nuxt", "storefront")
    for surface in SURFACES:
        if surface == "storefront-nuxt":
            continue
        assert surface not in services, f"{surface} voltou a ter service próprio (ADR-030)"
        group = _group_of(surface)
        assert group, f"{surface} fora dos grupos de operador"
        assert_image(group, group)
        app_id = surface.removesuffix("-nuxt")
        hosts = [
            pair.split("=", 1)[1]
            for pair in _env_map(services[group])["OPERATOR_HOSTS"].split(",")
            if pair.split("=", 1)[0] == app_id
        ]
        assert hosts, f"{surface} sem host em OPERATOR_HOSTS de {group}"
        for host in hosts:
            assert routes.get(host) == group, f"{host} ({surface}) não é roteado para {group}"

    source = (ROOT / ".do" / "app.alpha-subdomains.yaml").read_text()
    assert "compras.boulangerie.com.br" in source
    assert "SHOPMAN_PURCHASE_BASE_URL" in source


def test_operator_group_env_prefixes_name_apps_of_that_group():
    """`<APP>__CHAVE` só com APP do próprio grupo — o launcher recusa o resto no boot.

    Pegar aqui é pegar na CI em vez de no deploy vermelho da DigitalOcean.
    """
    import re

    import yaml

    groups = _operator_groups()
    every_id = {app["id"] for apps in groups.values() for app in apps}
    for path in DEPLOY_SPECS:
        spec = yaml.safe_load(path.read_text())
        services = {svc["name"]: svc for svc in spec.get("services") or []}
        for group, apps in groups.items():
            assert group in services, f"{path.name}: service {group} ausente"
            ids = {app["id"] for app in apps}
            for key in _env_map(services[group]):
                match = re.match(r"^([A-Z][A-Z0-9]*)__(.+)$", key)
                if not match:
                    continue
                app_id = match.group(1).lower()
                assert app_id in every_id, f"{path.name}: {key} tem prefixo que não é app"
                assert app_id in ids, f"{path.name}: {key} é de app fora de {group}"
                assert match.group(2) not in {"PORT", "HOST", "NITRO_PORT", "NITRO_HOST"}
            declared = {pair.split("=", 1)[0] for pair in _env_map(services[group])["OPERATOR_HOSTS"].split(",")}
            assert declared == ids, f"{path.name}: OPERATOR_HOSTS de {group} cobre {declared}, grupo é {ids}"


def test_operator_groups_report_capacity_as_one_service():
    """`NUXT_OPERATOR_SERVICE_NAME` é do SERVIÇO: sem prefixo, igual ao nome do grupo.

    O medidor de capacidade (#783) lê o cgroup do contêiner, que é um só para
    todos os filhos. Com prefixo por app (ou ausente), cada processo se
    reportaria com o próprio nome e sairia um alerta por app para o mesmo
    contêiner.
    """
    import yaml

    for path in DEPLOY_SPECS:
        spec = yaml.safe_load(path.read_text())
        services = {svc["name"]: svc for svc in spec.get("services") or []}
        for group in _operator_groups():
            envs = _env_map(services[group])
            assert envs.get("NUXT_OPERATOR_SERVICE_NAME") == group, f"{path.name}: {group} sem nome de serviço"
            per_app = [k for k in envs if k.endswith("__NUXT_OPERATOR_SERVICE_NAME")]
            assert not per_app, f"{path.name}: {group} sobrescreve o nome do serviço por app: {per_app}"


def test_operator_groups_have_capacity_alerts():
    import yaml

    for path in DEPLOY_SPECS:
        spec = yaml.safe_load(path.read_text())
        services = {svc["name"]: svc for svc in spec.get("services") or []}
        for group in _operator_groups():
            rules = {alert["rule"] for alert in services[group].get("alerts") or []}
            assert {"CPU_UTILIZATION", "MEM_UTILIZATION", "RESTART_COUNT"} <= rules, f"{path.name}: {group} sem alerta"


def test_alpha_probes_separate_liveness_from_dependency_readiness():
    import yaml

    spec = yaml.safe_load((ROOT / ".do" / "app.alpha-subdomains.yaml").read_text())
    services = {service["name"]: service for service in spec["services"]}

    assert services["web"]["liveness_health_check"]["http_path"] == "/health/live/"
    assert services["web"]["health_check"]["http_path"] == "/health/ready/"
    # Marketing mora no operator-office: a readiness do grupo agrega o
    # /health/ready do Marketing (com Django), a liveness agrega /health/live.
    office = services["operator-office"]
    assert office["liveness_health_check"]["http_path"] == "/health/live"
    assert office["health_check"]["http_path"] == "/health/ready"
    marketing_app = next(app for app in _operator_groups()["operator-office"] if app["id"] == "marketing")
    assert marketing_app.get("readyPath") == "/health/ready"
    floor = services["operator-floor"]
    assert floor["health_check"]["http_path"] == "/health/live"
    assert floor["liveness_health_check"]["http_path"] == "/health/live"

    marketing = ROOT / "surfaces" / "marketing-nuxt" / "server" / "routes" / "health"
    assert (marketing / "live.get.ts").is_file()
    assert (marketing / "ready.get.ts").is_file()
