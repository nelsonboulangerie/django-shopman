#!/usr/bin/env python
"""Run the runtime security/reliability subset and fail on any skipped test."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ⚠️ Esta tupla é a ÚNICA coisa que faz um teste marcado com ``requires_postgres``
# rodar em algum lugar. O ``make test`` roda em SQLite, então o ``skipif`` desses
# arquivos os pula SEMPRE; quem os executa é este gate, contra PostgreSQL + Redis
# reais, e ele reprova em qualquer skip.
#
# Consequência: um arquivo com ``requires_postgres`` que não esteja listado aqui
# não roda em lugar NENHUM — nem local, nem no CI — e ainda aparece verde no
# relatório como "passou (skipped)". Foi exatamente o que aconteceu com os quatro
# arquivos de corrida abaixo (venda simultânea, dupla submissão, cupom de uso
# único, fechar caixa com venda em voo, notificação duplicada): estavam escritos,
# revisados e mortos.
#
# Por isso ``test_runtime_gate.py::test_every_requires_postgres_file_is_listed``
# varre a árvore atrás do marcador e reprova quando um arquivo novo nasce fora
# desta lista. Ao criar um teste ``requires_postgres``, acrescente-o AQUI.
DEFAULT_RUNTIME_TEST_PATHS = (
    "packages/stockman/shopman/stockman/tests/test_concurrency.py",
    "packages/stockman/shopman/stockman/tests/test_quantity_invariant.py",
    "packages/payman/shopman/payman/tests/test_concurrency.py",
    "packages/craftsman/shopman/craftsman/tests/test_concurrency.py",
    "packages/cashman/shopman/cashman/tests/test_concurrency.py",
    "shopman/shop/tests/test_concurrent_finish_does_not_double_credit.py",
    "shopman/storefront/tests/test_concurrent_checkout.py",
    "shopman/storefront/tests/security/test_race_and_ratelimit.py",
    "shopman/shop/tests/integration/test_storefront_backstage_stress.py",
    "shopman/shop/tests/test_directive_dedupe.py",
    "shopman/shop/tests/test_commit_stock_gate.py",
    # O duplo-submit do PDV se defende com trava de LINHA, e trava de linha
    # não existe em SQLite: no `test-shop` o caso da corrida é pulado por
    # `requires_postgres` e some. Sem esta entrada, a única defesa contra
    # dois pedidos para uma venda não roda em CI nenhum — e este gate
    # existe exatamente para isso, porque reprova qualquer skip.
    "shopman/shop/tests/test_pos_cash_ledger.py",
    "shopman/storefront/tests/test_rate_limiting.py",
    "shopman/storefront/tests/web/test_order_access_security.py",
    "shopman/shop/tests/test_eventstream_permissions.py",
    "shopman/shop/tests/test_payment_webhooks.py",
    "shopman/shop/tests/test_ifood_webhook.py",
    "shopman/backstage/tests/test_gateway_smoke.py",
    "shopman/shop/tests/test_deploy_checks.py",
    "shopman/shop/tests/test_health.py",
)


@dataclass(eq=False)
class SkipCollector:
    skipped: list[tuple[str, str]] = field(default_factory=list)

    def pytest_runtest_logreport(self, report) -> None:
        if not report.skipped:
            return
        if report.when not in {"setup", "call"}:
            return
        reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else str(report.longrepr)
        self.skipped.append((report.nodeid, reason))


def _runtime_paths() -> list[str]:
    configured = os.environ.get("SHOPMAN_RUNTIME_TEST_PATHS", "").strip()
    if configured:
        return configured.split()
    return list(DEFAULT_RUNTIME_TEST_PATHS)


def main(argv: list[str] | None = None) -> int:
    try:
        import pytest
    except ImportError:
        print("pytest is required to run runtime tests.", file=sys.stderr)
        return 1

    collector = SkipCollector()
    extra_args = list(argv if argv is not None else sys.argv[1:])
    runtime_paths = _runtime_paths()
    print("Runtime test paths:", flush=True)
    for path in runtime_paths:
        print(f"- {path}", flush=True)

    pytest_args = [
        *runtime_paths,
        "-vv",
        "-s",
        "--maxfail=1",
        "-r",
        "s",
        "--durations=25",
        "--timeout=180",
        "--timeout-method=thread",
        *extra_args,
    ]
    result = pytest.main(pytest_args, plugins=[collector])

    if result == 0 and collector.skipped:
        print("\nRuntime gate failed because tests were skipped:", file=sys.stderr)
        for nodeid, reason in collector.skipped:
            print(f"- {nodeid}: {reason}", file=sys.stderr)
        return 1

    return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
