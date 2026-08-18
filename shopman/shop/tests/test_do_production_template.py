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

PRODUCTION_SPEC = (
    pathlib.Path(__file__).resolve().parents[3] / ".do" / "app.subdomains.yaml"
)

# Chaves que, ligadas, fazem o sistema fingir que foi pago.
PAYMENT_BYPASS_KEYS = (
    "SHOPMAN_MOCK_PIX_AUTO_CONFIRM",
    "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS",
)


def _envs(spec: dict):
    """Todo par (key, value) de env do blueprint, em qualquer serviço/job."""
    for section in ("envs", "services", "jobs", "workers", "static_sites"):
        block = spec.get(section) or []
        if section == "envs":
            yield from ((entry.get("key"), entry.get("value")) for entry in block)
            continue
        for component in block:
            for entry in component.get("envs") or []:
                yield entry.get("key"), entry.get("value")


def test_production_template_never_auto_confirms_payment():
    spec = yaml.safe_load(PRODUCTION_SPEC.read_text())
    offenders = [
        key
        for key, value in _envs(spec)
        if key in PAYMENT_BYPASS_KEYS and str(value).strip().lower() == "true"
    ]
    assert not offenders, (
        "template de PRODUÇÃO com bypass de pagamento ligado: "
        + ", ".join(sorted(offenders))
    )
