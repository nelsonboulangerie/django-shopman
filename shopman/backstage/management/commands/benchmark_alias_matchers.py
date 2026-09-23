"""Piloto do de-para de produto: fuzzy × Jev × LLM × embeddings contra o gabarito confirmado.

Invólucro de ``shopman.backstage.bi.matcher_benchmark``: escolhe concorrentes,
roda, imprime o placar (acerto, o que aceitaria sozinho e quanto disso errado,
latência, tokens, custo) e, com ``--csv``, grava caso a caso para auditoria.
Não grava alias nenhum.

Preços em US$ por milhão de tokens. O default do Jev é o preço de lançamento
(entrada US$ 0,042/M, saída grátis); o de cada LLM vem de ``LLM_PRICES``.
``--*-price-*`` sobrescrevem (os de LLM valem para todos os ``--llm-model``);
modelo fora da tabela sai com custo zerado e o relatório avisa.
"""

from __future__ import annotations

import csv

from django.core.management.base import BaseCommand, CommandError

from shopman.backstage.bi.mapping import DEFAULT_MIN_SCORE
from shopman.backstage.bi.matcher_benchmark import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_SHORTLIST,
    build_matchers,
    gold_cases,
    load_catalog,
    prices_for,
    run,
)

MATCHERS = ("fuzzy", "jev", "llm", "embed")


class Command(BaseCommand):
    help = "Mede fuzzy, Jev, LLM e embeddings no de-para de produto contra os de-paras confirmados. Não grava nada."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="yooga", help="Origem do histórico (default: yooga).")
        parser.add_argument(
            "--matcher", choices=MATCHERS, action="append",
            help="Concorrente; repetível. Sem --matcher, todos (quem não tiver credencial ou pacote fica de fora).",
        )
        parser.add_argument(
            "--llm-model", action="append",
            help="Modelo do concorrente llm; repetível (ex.: claude-haiku-4-5). Default: AI_ASSIST_MODEL.",
        )
        parser.add_argument(
            "--embedding-model", default=DEFAULT_EMBEDDING_MODEL,
            help=f"Modelo de embeddings do fastembed (default {DEFAULT_EMBEDDING_MODEL}).",
        )
        parser.add_argument(
            "--min-similarity", type=float, default=DEFAULT_MIN_SIMILARITY,
            help=f"Corte de similaridade dos embeddings, 0–1 (default {DEFAULT_MIN_SIMILARITY}).",
        )
        parser.add_argument("--limit", type=int, default=200, help="Máximo de casos do gabarito (default 200).")
        parser.add_argument(
            "--shortlist", type=int, default=DEFAULT_SHORTLIST,
            help=f"Candidatos que Jev e LLM veem (default {DEFAULT_SHORTLIST}).",
        )
        parser.add_argument(
            "--accept-at", type=float, default=0.9,
            help="Confiança a partir da qual o concorrente aceitaria sozinho (default 0.9).",
        )
        parser.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE, help="Corte do fuzzy (default 80).")
        parser.add_argument("--jev-price-in", type=float, default=0.042, help="US$/M tokens de entrada do Jev.")
        parser.add_argument("--jev-price-out", type=float, default=0.0, help="US$/M tokens de saída do Jev.")
        parser.add_argument("--llm-price-in", type=float, help="US$/M tokens de entrada do LLM (default: LLM_PRICES).")
        parser.add_argument("--llm-price-out", type=float, help="US$/M tokens de saída do LLM (default: LLM_PRICES).")
        parser.add_argument("--csv", help="Grava o resultado caso a caso neste arquivo.")

    def handle(self, *args, **options):
        if not 0 < options["accept_at"] <= 1:
            raise CommandError("--accept-at vai de 0 (exclusive) a 1.")
        if not 0 <= options["min_similarity"] <= 1:
            raise CommandError("--min-similarity vai de 0 a 1.")
        requested = options["matcher"] or list(MATCHERS)
        explicit = bool(options["matcher"])

        matchers, skipped = build_matchers(
            requested,
            llm_models=options["llm_model"],
            min_score=options["min_score"],
            embedding_model=options["embedding_model"],
            min_similarity=options["min_similarity"],
        )
        for name, reason in skipped:
            if explicit:
                raise CommandError(reason)
            self.stdout.write(self.style.WARNING(f"{name}: fora do placar — {reason}"))

        cases = gold_cases(options["source"], limit=options["limit"])
        if not cases:
            raise CommandError(
                f"Gabarito vazio: nenhum de-para de produto confirmado para '{options['source']}'. "
                "Confirme alguns em Admin → B.I. → De-paras e rode de novo."
            )
        catalog = load_catalog()
        prices, self.unpriced = prices_for(
            matchers,
            llm_price_in=options["llm_price_in"],
            llm_price_out=options["llm_price_out"],
            jev_price_in=options["jev_price_in"],
            jev_price_out=options["jev_price_out"],
        )
        result = run(
            cases, catalog, matchers, prices=prices,
            shortlist_size=options["shortlist"], accept_at=options["accept_at"],
        )
        self._report(result, options)
        if options["csv"]:
            self._write_csv(result, catalog, options["csv"])

    def _report(self, result, options) -> None:
        with_product = result.cases_with_product
        coverage = f"{result.shortlist_hits}/{with_product}" if with_product else "—"
        self.stdout.write(self.style.SUCCESS(
            f"\n═══ De-para de produto: {result.cases} casos confirmados de '{options['source']}' "
            f"({with_product} com produto, {result.cases - with_product} fora do catálogo) ═══"
        ))
        self.stdout.write(
            f"Lista curta de {result.shortlist_size}: o produto certo estava nela em {coverage} "
            "— é o teto de acerto de Jev e LLM.\n"
        )
        width = max([6, *(len(board.matcher) for board in result.boards)])
        header = f"  {'':<{width}} {'acerto':>13} {'aceitaria sozinho (errados)':>28} {'p50 ms':>8} {'p95 ms':>8} {'tokens in/out':>15} {'US$':>9} {'US$/1k':>8} {'falhas':>7}"
        self.stdout.write(header)
        for board in result.boards:
            per_thousand = board.cost_usd / board.total * 1000 if board.total else 0.0
            p50, p95 = board.latency(0.5), board.latency(0.95)
            self.stdout.write(
                f"  {board.matcher:<{width}} "
                f"{f'{board.correct}/{board.total} ({board.correct / board.total:.0%})':>13} "
                f"{f'{board.accepted} ({board.accepted_wrong})':>28} "
                f"{f'{p50:.0f}' if p50 is not None else '—':>8} "
                f"{f'{p95:.0f}' if p95 is not None else '—':>8} "
                f"{f'{board.input_tokens}/{board.output_tokens}':>15} "
                f"{board.cost_usd:>9.4f} {per_thousand:>8.4f} {board.errors:>7}"
            )
        self.stdout.write(
            f"\n'Aceitaria sozinho' = confiança ≥ {options['accept_at']}; o número entre parênteses é o erro "
            "que passaria sem ninguém ver. Latência do fuzzy não é medida (local, sem rede); a do embed é "
            "local (sem rede). O embed procura no catálogo inteiro, sem a lista curta."
        )
        for model in self.unpriced:
            self.stdout.write(self.style.WARNING(
                f"Custo de llm:{model} zerado: modelo fora da tabela; passe --llm-price-in/--llm-price-out."
            ))
        for board in result.boards:
            failures = [row for row in board.rows if row[5]]
            if failures:
                self.stdout.write(self.style.WARNING(f"{board.matcher}: {len(failures)} falhas; a primeira: {failures[0][5]}"))
        self.stdout.write("Nada foi gravado: o piloto só mede.")

    def _write_csv(self, result, catalog, path: str) -> None:
        sku_by_pk = {entry.pk: entry.sku for entry in catalog}
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["concorrente", "nome_na_origem", "esperado", "escolhido", "confianca", "acertou", "falha"])
            for board in result.boards:
                for name, expected, chosen, confidence, right, error in board.rows:
                    writer.writerow([
                        board.matcher, name,
                        sku_by_pk.get(expected, "—"), sku_by_pk.get(chosen, "—"),
                        "" if confidence is None else f"{confidence:.3f}",
                        "sim" if right else "não", error,
                    ])
        self.stdout.write(f"Caso a caso em {path}.")
