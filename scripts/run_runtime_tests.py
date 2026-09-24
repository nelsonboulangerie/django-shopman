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
    "shopman/storefront/tests/test_operational_postgres.py",
    # Exclusão de conta compartilha a trava canônica do Customer com novos
    # pedidos, inscrições e mensagens; as três corridas exigem conexões reais.
    "shopman/storefront/tests/test_account_privacy_postgres.py",
    # Session anonimizada é um selo irreversível: writers atrasados esperam
    # a trava e não podem restaurar handle, customer/data ou meta pessoal.
    "shopman/shop/tests/test_session_privacy_fence_postgres.py",
    # Eventos operacionais continuam depois da retenção do pedido, mas um
    # writer stale não pode recolocar note/reason após a anonimização.
    "shopman/shop/tests/test_order_event_privacy_fence_postgres.py",
    # Login OTP resolves by contact before waiting for the canonical Customer
    # row.  This proof ensures a contact change that wins that lock prevents
    # both delivery and verification against the stale phone/email owner.
    "packages/doorman/shopman/doorman/tests/test_verification_ownership_postgres.py",
    # The export must finish one coherent snapshot while holding the same
    # canonical Customer fence used by deletion; neither mixed artifacts nor a
    # completed receipt for a preempted export are acceptable.
    "shopman/storefront/tests/test_account_export_postgres.py",
    # O perfil e o persist composto do PDV gravam metadata, contatos,
    # identificadores e enderecos; a exclusao precisa vencer sem que esses
    # filhos pessoais sejam recriados por uma instancia stale.
    "shopman/shop/tests/test_pos_privacy_postgres.py",
    # Identity binding writes phone/name/customer_ref back to a conversation.
    # These races prove deletion cannot be followed by stale PII recreation.
    "shopman/storefront/tests/test_concierge_privacy_postgres.py",
    # ManyChat can attach identifiers and contact data while account deletion
    # runs. The shared Customer fence decides the winner without recreating PII.
    # ⚠️ Este arquivo morava em `packages/guestman/` e NUNCA rodou: o rootdir
    # de `packages/guestman` carrega `guestman_test_settings`, que não instala
    # `shopman.shop`, então o skip de módulo disparava — inclusive no CI. E
    # skip de MÓDULO não passa pelo coletor deste gate, então ele nem reprovava.
    # As provas são da exclusão (monolito), e é aqui que elas rodam de verdade.
    "shopman/storefront/tests/test_manychat_privacy_postgres.py",
    # Public Guestman child writers share the Customer-first privacy fence;
    # loyalty additionally proves it never takes LoyaltyAccount first.
    "packages/guestman/shopman/guestman/tests/test_privacy_mutation_fences_postgres.py",
    # Provas do concierge dependem de locks, conexões independentes e migrações
    # reais; skips do lote SQLite precisam executar neste gate estrito.
    "shopman/storefront/tests/test_concierge_authority.py",
    "shopman/storefront/tests/test_concierge_commercial_races.py",
    "shopman/storefront/tests/test_concierge_consent_race.py",
    "shopman/storefront/tests/test_concierge_payment_race.py",
    "shopman/storefront/tests/test_concierge_boundary_races.py",
    "shopman/storefront/tests/test_concierge_whatsapp_window.py",
    "shopman/storefront/tests/test_concierge_runtime_turns.py",
    "shopman/storefront/tests/test_concierge_runtime_fulfillment.py",
    "shopman/storefront/tests/test_concierge_runtime_load.py",
    "shopman/storefront/tests/test_concierge_runtime_migration.py",
    "shopman/storefront/tests/test_concierge_runtime_vertical.py",
    "shopman/storefront/tests/security/test_race_and_ratelimit.py",
    "shopman/shop/tests/integration/test_storefront_backstage_stress.py",
    "shopman/shop/tests/test_directive_dedupe.py",
    "shopman/shop/tests/test_waitlist_lifecycle.py",
    "shopman/shop/tests/test_commit_stock_gate.py",
    # O duplo-submit do PDV se defende com trava de LINHA, e trava de linha
    # não existe em SQLite: no `test-shop` o caso da corrida é pulado por
    # `requires_postgres` e some. Sem esta entrada, a única defesa contra
    # dois pedidos para uma venda não roda em CI nenhum — e este gate
    # existe exatamente para isso, porque reprova qualquer skip.
    "shopman/shop/tests/test_pos_cash_ledger.py",
    # O claim de webhook só quebra com o abort de transação do Postgres:
    # em SQLite o IntegrityError não envenena o bloco, e a corrida passa.
    "shopman/shop/tests/test_webhook_claim_race.py",
    "shopman/storefront/tests/test_rate_limiting.py",
    "shopman/storefront/tests/web/test_order_access_security.py",
    "shopman/shop/tests/test_eventstream_permissions.py",
    "shopman/shop/tests/test_payment_webhooks.py",
    "shopman/shop/tests/test_ifood_webhook.py",
    # Public publications have no audience member. PostgreSQL renders the
    # hydrated ``member__customer`` path as an OUTER JOIN and rejects a broad
    # ``FOR UPDATE``; this regression only exists on the real database.
    "shopman/shop/tests/test_marketing_delivery_postgres.py",
    # O ciclo expand/rollback/reapply da 0053 precisa rodar no PostgreSQL real:
    # SQLite não prova compatibilidade do writer 0052 com defaults/constraints
    # do schema expandido nem a reversão transacional do banco de produção.
    "shopman/shop/tests/test_marketing_capabilities.py",
    "shopman/backstage/tests/test_gateway_smoke.py",
    "shopman/backstage/tests/test_pos_tab_revision_boundary.py",
    "shopman/backstage/tests/test_planning_idempotency_race.py",
    "shopman/backstage/tests/test_kds_lock_order_postgresql.py",
    # Dois relays da mesma estação não podem capturar/imprimir a mesma etiqueta.
    # A garantia depende de SELECT FOR UPDATE SKIP LOCKED no PostgreSQL real.
    "shopman/backstage/tests/test_production_print_jobs_postgresql.py",
    "shopman/shop/tests/test_deploy_checks.py",
    "shopman/shop/tests/test_health.py",
)


def _reason(longrepr) -> str:
    return longrepr[2] if isinstance(longrepr, tuple) else str(longrepr)


@dataclass(eq=False)
class SkipCollector:
    """Reprova o gate em qualquer forma de "não rodou", não só na visível.

    Havia um buraco do tamanho do problema: ``pytest_runtest_logreport`` só
    existe para teste que chegou a ser COLETADO. Um módulo que se pula sozinho
    na coleta — ``pytest.skip(..., allow_module_level=True)``, o padrão de quem
    escreve integração monolítica dentro de um pacote cujas settings não
    instalam ``shopman.shop`` — não produz report de execução nenhum: o pytest
    imprime ``0 collected, 1 skipped`` e sai com 0. O gate lia esse 0 e dizia
    verde.

    O que torna o buraco perigoso é que esse skip depende do ``rootdir``, e o
    ``rootdir`` depende dos argumentos. Medido em 23/09/2026 com
    ``packages/doorman/.../test_verification_ownership_postgres.py``: rodado
    SOZINHO, o ``rootdir`` é ``packages/doorman``, as settings são
    ``doorman_test_settings`` (sem ``shopman.shop``) e o módulo se pula —
    ``0 collected, 1 skipped``, saída 0. Rodado com a lista inteira, o
    ``rootdir`` é a raiz, as settings são ``config.settings`` e os cinco testes
    rodam e passam (conferido no log da fila de merge do PR #989, 23/09 10:00).

    Ou seja: o mesmo arquivo roda ou não roda conforme quem o invoca, e até
    aqui o gate não sabia a diferença. Enquanto ele responder 0 a um módulo
    pulado, "coberto pelo gate" é uma afirmação que ninguém verifica — e o dia
    em que uma settings mudar, a cobertura evapora em silêncio.

    Por isso são três redes, e não uma:

    1. ``pytest_runtest_logreport`` — o skip de teste, que já existia;
    2. ``pytest_collectreport`` — o skip de MÓDULO, invisível à primeira;
    3. ``pytest_itemcollected`` + ``collected_files`` — o catch-all: arquivo
       listado que não entregou NENHUM teste reprova, qualquer que tenha sido
       o mecanismo (skip de coleta, arquivo esvaziado, rename silencioso).

    A terceira usa ``pytest_itemcollected`` de propósito, e não a lista final de
    ``pytest_collection_modifyitems``: aquele hook roda por item durante a
    coleta, antes de qualquer desseleção, então um ``-k`` de quem está depurando
    não vira reprovação falsa.
    """

    skipped: list[tuple[str, str]] = field(default_factory=list)
    collect_skipped: list[tuple[str, str]] = field(default_factory=list)
    collected_files: set[Path] = field(default_factory=set)

    def pytest_runtest_logreport(self, report) -> None:
        if not report.skipped:
            return
        if report.when not in {"setup", "call"}:
            return
        self.skipped.append((report.nodeid, _reason(report.longrepr)))

    def pytest_collectreport(self, report) -> None:
        if not report.skipped:
            return
        self.collect_skipped.append((report.nodeid, _reason(report.longrepr)))

    def pytest_itemcollected(self, item) -> None:
        path = getattr(item, "path", None)
        if path is None:
            return
        self.collected_files.add(Path(str(path)).resolve())

    def empty_paths(self, runtime_paths: list[str]) -> list[str]:
        """Caminhos pedidos que não entregaram um único teste."""
        return [path for path in runtime_paths if (ROOT / path).resolve() not in self.collected_files]


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

    violations = False

    if collector.skipped:
        violations = True
        print("\nRuntime gate failed because tests were skipped:", file=sys.stderr)
        for nodeid, reason in collector.skipped:
            print(f"- {nodeid}: {reason}", file=sys.stderr)

    if collector.collect_skipped:
        violations = True
        print("\nRuntime gate failed because whole modules were skipped at collection:", file=sys.stderr)
        for nodeid, reason in collector.collect_skipped:
            print(f"- {nodeid}: {reason}", file=sys.stderr)

    # `--maxfail=1` interrompe a EXECUÇÃO, não a coleta: os arquivos seguintes
    # já foram coletados e continuam contando. Mas se a própria coleta abortou
    # (erro de import), a lista fica curta e "vazio" seria mentira — por isso a
    # varredura de coleta vazia só vale quando nada falhou na execução.
    if not violations and result == 0:
        empty = collector.empty_paths(runtime_paths)
        if empty:
            violations = True
            print(
                "\nRuntime gate failed because listed files collected zero tests "
                "(they are declared covered and do not run):",
                file=sys.stderr,
            )
            for path in empty:
                print(f"- {path}", file=sys.stderr)

    if violations and result == 0:
        return 1

    return int(result)


if __name__ == "__main__":
    raise SystemExit(main())
