"""Propõe de-paras do B.I. a partir do histórico carregado. Nunca confirma.

Invólucro de ``shopman.backstage.bi.mapping``: traduz argumentos, imprime o
que foi proposto e para onde ir para confirmar (Admin → B.I.). As regras
(SKU exato antes de nome parecido; o que já tem alias não volta; o que não
casou fica na fila com o melhor palpite) moram no módulo, com o motivo.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from shopman.backstage.bi.mapping import (
    DEFAULT_MIN_SCORE,
    suggest_categories,
    suggest_payments,
    suggest_products,
)

KINDS = ("product", "category", "payment")


class Command(BaseCommand):
    help = "Propõe de-paras (produto, categoria, forma de pagamento) a partir do histórico; nada é confirmado."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="yooga", help="Origem do histórico (default: yooga).")
        parser.add_argument(
            "--kind", choices=KINDS, action="append",
            help="Que de-para propor; repetível. Sem --kind, os três.",
        )
        parser.add_argument(
            "--min-score", type=int, default=DEFAULT_MIN_SCORE,
            help=f"Corte do nome parecido, 0–100 (default {DEFAULT_MIN_SCORE}). Abaixo, fica na fila sem produto.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Mostra o que proporia, sem gravar.")
        parser.add_argument("--limit", type=int, default=40, help="Linhas mostradas por tabela (default 40).")

    def handle(self, *args, **options):
        if not 0 <= options["min_score"] <= 100:
            raise CommandError("--min-score vai de 0 a 100.")
        kinds = options["kind"] or list(KINDS)
        dry_run = options["dry_run"]
        for kind in kinds:
            if kind == "product":
                result = suggest_products(options["source"], min_score=options["min_score"], dry_run=dry_run)
            elif kind == "category":
                result = suggest_categories(dry_run=dry_run)
            else:
                result = suggest_payments(dry_run=dry_run)
            self._report(result, dry_run=dry_run, limit=options["limit"])
        self.stdout.write(
            "\nNada foi confirmado: a leitura só usa de-para confirmado. "
            "Confira em Admin → B.I. → De-paras."
            + (" (--dry-run: nada gravado.)" if dry_run else "")
        )

    def _report(self, result, *, dry_run: bool, limit: int) -> None:
        title = {"product": "produto", "category": "categoria", "payment": "forma de pagamento"}[result.kind]
        verb = "Proporia" if dry_run else "Propostos"
        self.stdout.write(self.style.SUCCESS(
            f"\n═══ De-para de {title}: {verb} {result.created} "
            f"({result.matched} com alvo, {result.unmatched} na fila; {result.skipped_existing} já tinham alias) ═══"
        ))
        for key, target, score, note in result.rows[:limit]:
            score_text = f"{score:>3}" if score != "" else "   "
            self.stdout.write(f"  {key[:36]:<36} → {target:<20} {score_text}  {note}")
        if len(result.rows) > limit:
            self.stdout.write(f"  … e mais {len(result.rows) - limit} (use --limit).")
