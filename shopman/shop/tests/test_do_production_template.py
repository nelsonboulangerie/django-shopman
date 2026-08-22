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
