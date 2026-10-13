"""purge_synthetic_data: apaga o sintético do ensaio e deixa o cadastro do Dia 1.

Passo "Dia D · dados" do cutover (docs/runbooks/go-live-cutover.md §0a, D-029):
a loja vira produção no próprio app, no mesmo banco. A política (o que sai, o
que fica e por quê) mora em ``config/synthetic_purge.py``.

    python manage.py purge_synthetic_data                      # ensaio: executa, mede e desfaz
    python manage.py purge_synthetic_data --json relatorio.json
    python manage.py purge_synthetic_data --apply --confirm-database shopman

O ``--apply`` exige o nome do banco digitado (``--confirm-database``) e recusa
quando a política do go-live já está armada (``SHOPMAN_GO_LIVE``/tag
``go-live-v1``) ou o ambiente é ``production``: depois da virada, o que este
comando apaga é dado de verdade. Idempotente: a segunda rodada não acha nada.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from config import synthetic_purge
from shopman.shop.migration_safety import go_live_active


class Command(BaseCommand):
    help = "Apaga o dado do ensaio (pedidos, clientes, caixa, produção, estoque) e mantém o cadastro do Dia 1. Ensaio por padrão."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Grava. Sem isto o comando executa, mede e desfaz.",
        )
        parser.add_argument(
            "--confirm-database", default="",
            help="Nome do banco de destino, digitado. Obrigatório com --apply.",
        )
        parser.add_argument("--json", dest="json_path", help="Grava o relatório completo neste arquivo novo.")

    def handle(self, *args, **options):
        apply = options["apply"]
        database = str(connections["default"].settings_dict.get("NAME"))
        if apply:
            self._guard_apply(database, options["confirm_database"])

        try:
            report = synthetic_purge.run(apply=apply)
        except (synthetic_purge.PolicyError, synthetic_purge.PurgeAborted) as exc:
            raise CommandError(f"Nada foi gravado.\n{exc}") from exc

        self._render(report)
        if options["json_path"]:
            path = Path(options["json_path"])
            if path.exists():
                raise CommandError(f"{path} já existe; escolha outro caminho para não perder o relatório anterior.")
            path.write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.stdout.write(f"Relatório completo em {path}.")

    def _guard_apply(self, database: str, typed: str) -> None:
        if typed != database:
            raise CommandError(
                f"Para gravar, digite o nome do banco: --confirm-database {database}. Nada foi gravado."
            )
        armed, why = go_live_active()
        if armed:
            raise CommandError(f"A política do go-live está armada ({why}): o dado deste banco é real. Nada foi gravado.")
        environment = str(getattr(settings, "SHOPMAN_ENVIRONMENT", "") or "").lower()
        if environment == "production":
            raise CommandError("SHOPMAN_ENVIRONMENT=production: o dado deste banco é real. Nada foi gravado.")

    def _render(self, report: synthetic_purge.Report) -> None:
        out = self.stdout
        verb = "Apagado" if report.applied else "Apagaria"
        out.write(f"\nBanco: {report.database}  ·  {'GRAVADO' if report.applied else 'ensaio (nada gravado)'}\n")

        out.write(f"\n{verb} (dado do ensaio):")
        for label, rule, before, after in report.rows():
            if rule.action != synthetic_purge.KEEP and before != after:
                out.write(f"  {label:<48} {before:>7} → {after:<7} {rule.reason}")
        total = report.removed(synthetic_purge.PURGE) + report.removed(synthetic_purge.PURGE_ROWS)
        out.write(f"  {'total':<48} {total:>7} linhas")

        if report.cascade or report.detached:
            out.write("\nLevado junto pelas contas de cliente / ponteiros esvaziados:")
            for label, n in sorted(report.cascade.items()):
                out.write(f"  {label:<48} {n:>7}")
            for label, n in sorted(report.detached.items()):
                out.write(f"  {label:<48} {n:>7} (FK esvaziada)")

        kept = [(label, before) for label, rule, before, _a in report.rows() if rule.action == synthetic_purge.KEEP and before]
        out.write(f"\nMantido (cadastro do Dia 1): {len(kept)} tabelas com linhas, contagem conferida.")
        for label, before in kept:
            out.write(f"  {label:<48} {before:>7}")

        portrait = report.portrait
        out.write("\nRetrato do Dia 1:")
        for key in (
            "products", "products_on_sale", "products_sellable_unpublished", "recipes_active",
            "materials", "suppliers", "rules_active", "stock_quants", "customers", "orders",
        ):
            out.write(f"  {key:<32} {portrait.get(key)}")
        for ref, entry in portrait.get("listings", {}).items():
            out.write(f"  listing {ref:<24} {entry['on_sale']} à venda de {entry['items']}")
        out.write(f"  canais ativos: {', '.join(portrait.get('channels_active', []))}")
        out.write(f"  promoções ativas: {', '.join(portrait.get('promotions_active', [])) or '(nenhuma)'}")
        out.write(f"  cupons ativos: {', '.join(portrait.get('coupons_active', [])) or '(nenhum)'}")
        for username, info in portrait.get("accounts", {}).items():
            role = ", ".join(info["groups"]) or "sem papel"
            out.write(f"  conta {username:<16} {role}{' · PIN' if info['pin'] else ''}")

        out.write(
            "\nDepois do --apply: inventário de abertura contado (o estoque fica zerado), "
            "`refresh_bi_daily_series --all` e o `compute_product_affinity` do worker."
        )
