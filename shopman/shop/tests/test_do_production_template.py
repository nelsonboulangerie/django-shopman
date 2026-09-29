"""O template de produção não pode nascer com pagamento se autoconfirmando.

`SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true` estava no blueprint de **produção**. É
inerte enquanto o deploy-check `SHOPMAN_E003` barra `payment_mock` em produção,
mas fica PRÉ-ARMADO: no dia em que alguém ligar
`SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true` para destravar um deploy, todo PIX
passa a se autoconfirmar de graça — pedido entregue sem pagamento, sem que
nenhum outro check reclame.

Duas travas são melhores que uma justamente porque a primeira será desligada
sob pressão, num deploy travado, tarde da noite. Staging fica de fora: lá o
mock é a intenção.
"""

from __future__ import annotations

import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]
PRODUCTION_SPEC = ROOT / ".do" / "app.subdomains.yaml"
DEPLOY_SPECS = (
    PRODUCTION_SPEC,
    ROOT / ".do" / "app.alpha-subdomains.yaml",
)

# Chaves que, ligadas, fazem o sistema fingir que foi pago.
PAYMENT_BYPASS_KEYS = (
    "SHOPMAN_MOCK_PIX_AUTO_CONFIRM",
    "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS",
    "SHOPMAN_EXPOSE_MOCK_CAPTURE",
)

# Uma credencial ou um teste anterior não pode deixar uma via de publicação
# pública armada no próximo deploy. A janela real é configuração operacional
# temporária e volta a false ao terminar.
MARKETING_PUBLICATION_CANARY_KEYS = (
    "SHOPMAN_MARKETING_PUBLICATION_CANARY_ENABLED",
    "SHOPMAN_MARKETING_INSTAGRAM_PUBLICATION_ENABLED",
    "SHOPMAN_MARKETING_FACEBOOK_PUBLICATION_ENABLED",
    "SHOPMAN_MARKETING_GOOGLE_PUBLICATION_ENABLED",
)

# The release gate must remain visible in the App Platform logs and must stop
# the PRE_DEPLOY job before touching the schema.  Keep these as full commands:
# loose substring checks would accept `migration_safety --report`, which always
# exits successfully and therefore disables the protection.
RELEASE_GUARD_PREFIX = (
    "python manage.py check --deploy",
    "python manage.py migration_safety",
    "python manage.py migrate --noinput",
)


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _load_spec(path: pathlib.Path) -> dict:
    return yaml.load(path.read_text(), Loader=UniqueKeyLoader)


def _env_entries(spec: dict):
    for entry in spec.get("envs") or []:
        yield entry
    for section in ("services", "jobs", "workers", "static_sites"):
        for component in spec.get(section) or []:
            for entry in component.get("envs") or []:
                yield entry


def _envs(spec: dict):
    """Todo par (key, value) de env do blueprint, em qualquer serviço/job."""
    for entry in _env_entries(spec):
        yield entry.get("key"), entry.get("value")


def _release_job(spec: dict, *, path: pathlib.Path) -> dict:
    jobs = [job for job in spec.get("jobs") or [] if job.get("name") == "release"]
    assert len(jobs) == 1, f"{path.name}: esperado exatamente um job release"
    return jobs[0]


def test_do_specs_have_unique_yaml_keys():
    for path in DEPLOY_SPECS:
        _load_spec(path)


def test_do_specs_env_entries_are_complete():
    for path in DEPLOY_SPECS:
        spec = _load_spec(path)
        for entry in _env_entries(spec):
            key = entry.get("key") or "<sem key>"
            assert entry.get("scope"), f"{path.name}: env {key} sem scope"
            assert entry.get("type"), f"{path.name}: env {key} sem type"


def test_release_jobs_fail_closed_before_migrate():
    for path in DEPLOY_SPECS:
        release = _release_job(_load_spec(path), path=path)
        assert release.get("kind") == "PRE_DEPLOY", (
            f"{path.name}: release precisa bloquear o deploy antes de subir a versao"
        )

        # YAML may fold the command over multiple lines.  Normalize whitespace
        # before checking the shell contract, but keep command boundaries exact.
        command = " ".join(str(release.get("run_command") or "").split())
        assert command.startswith("sh -c '") and command.endswith("'"), (
            f"{path.name}: release precisa usar um unico pipeline fail-closed"
        )
        pipeline = command[len("sh -c '") : -1]
        assert ";" not in pipeline and "||" not in pipeline, (
            f"{path.name}: release nao pode contornar falhas no gate de migrations"
        )

        stages = pipeline.split(" && ")
        assert tuple(stages[:3]) == RELEASE_GUARD_PREFIX, (
            f"{path.name}: ordem obrigatoria e check --deploy -> migration_safety -> migrate --noinput"
        )
        assert "python manage.py setup_groups" in stages[3:], (
            f"{path.name}: setup_groups deve rodar somente depois do migrate"
        )


def test_production_template_never_auto_confirms_payment():
    spec = _load_spec(PRODUCTION_SPEC)
    offenders = [
        key
        for key, value in _envs(spec)
        if key in PAYMENT_BYPASS_KEYS and str(value).strip().lower() == "true"
    ]
    assert not offenders, (
        "template de PRODUÇÃO com bypass de pagamento ligado: "
        + ", ".join(sorted(offenders))
    )


def test_deploy_templates_never_prearm_publication_canary():
    for path in DEPLOY_SPECS:
        spec = _load_spec(path)
        offenders = [
            key
            for key, value in _envs(spec)
            if key in MARKETING_PUBLICATION_CANARY_KEYS
            and str(value).strip().lower() == "true"
        ]
        assert not offenders, (
            f"{path.name}: via pública de canário pré-armada: "
            + ", ".join(sorted(offenders))
        )
