"""Piloto de intenções: regex × embeddings × LLM × Jev contra o gabarito rotulado.

Invólucro de ``shopman.storefront.concierge.intent_benchmark``: escolhe
concorrentes, roda, imprime o placar e, com ``--csv``, grava caso a caso
(número da amostra, intenções do gabarito e previstas, confianças) para
calibrar cortes. O CSV não leva texto de cliente: o texto se lê no Admin pela
amostra. Não grava nada no banco.

LLM e Jev só entram com ``SHOPMAN_INTENT_PILOT_EXTERNAL_APPROVED=true``: sem
isso, saem do placar dizendo por quê.
"""

from __future__ import annotations

import csv

from django.core.management.base import BaseCommand, CommandError

from shopman.shop.services.ai_pricing import LLM_PRICES, Price
from shopman.storefront.concierge.intent_benchmark import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MIN_SIMILARITY,
    ContenderNotConfigured,
    EmbeddingContender,
    JevContender,
    LLMContender,
    RegexContender,
    gold_samples,
    load_categories,
    run,
)

CONTENDERS = ("regex", "embed", "llm", "jev")


def _pct(value) -> str:
    return "—" if value is None else f"{value:.0%}"


class Command(BaseCommand):
    help = "Mede classificadores de intenção contra as mensagens rotuladas no Admin. Não grava nada."

    def add_arguments(self, parser):
        parser.add_argument(
            "--contender", choices=CONTENDERS, action="append",
            help="Concorrente; repetível. Sem --contender, todos (quem não puder rodar fica de fora, com o motivo).",
        )
        parser.add_argument("--limit", type=int, default=500, help="Máximo de amostras rotuladas (default 500).")
        parser.add_argument(
            "--llm-model", action="append",
            help="Modelo do concorrente llm; repetível (ex.: claude-haiku-4-5). Default: AI_ASSIST_MODEL.",
        )
        parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL, help="Modelo do fastembed.")
        parser.add_argument(
            "--min-similarity", type=float, default=DEFAULT_MIN_SIMILARITY,
            help=f"Corte dos embeddings, 0–1 (default {DEFAULT_MIN_SIMILARITY}).",
        )
        parser.add_argument("--jev-price-in", type=float, default=0.042, help="US$/M tokens de entrada do Jev.")
        parser.add_argument("--llm-price-in", type=float, help="US$/M tokens de entrada do LLM (default: tabela).")
        parser.add_argument("--llm-price-out", type=float, help="US$/M tokens de saída do LLM (default: tabela).")
        parser.add_argument("--csv", help="Grava o resultado caso a caso neste arquivo (sem texto de cliente).")

    def handle(self, *args, **options):
        if not 0 <= options["min_similarity"] <= 1:
            raise CommandError("--min-similarity vai de 0 a 1.")
        requested = options["contender"] or list(CONTENDERS)
        explicit = bool(options["contender"])

        contenders = []
        for name in requested:
            try:
                if name == "regex":
                    contenders.append(RegexContender())
                elif name == "embed":
                    contenders.append(EmbeddingContender(
                        model=options["embedding_model"], min_similarity=options["min_similarity"],
                    ))
                elif name == "llm":
                    for model in options["llm_model"] or [None]:
                        contenders.append(LLMContender(model=model))
                else:
                    contenders.append(JevContender())
            except ContenderNotConfigured as exc:
                if explicit:
                    raise CommandError(str(exc)) from exc
                self.stdout.write(self.style.WARNING(f"{name}: fora do placar — {exc}"))

        categories = load_categories()
        if not categories:
            raise CommandError("Sem intenções ativas. Rode setup_intent_categories ou crie no Admin.")
        samples = gold_samples(limit=options["limit"])
        if not samples:
            raise CommandError(
                "Gabarito vazio: nenhuma mensagem rotulada. Rode sample_intent_messages e rotule em "
                "Admin → Clientes → Mensagens para rotular."
            )

        prices = {"jev": Price(options["jev_price_in"], 0.0)}
        unpriced = []
        for contender in contenders:
            if isinstance(contender, LLMContender):
                table_in, table_out = LLM_PRICES.get(contender.model, (None, None))
                price_in = options["llm_price_in"] if options["llm_price_in"] is not None else table_in
                price_out = options["llm_price_out"] if options["llm_price_out"] is not None else table_out
                if price_in is None or price_out is None:
                    unpriced.append(contender.model)
                prices[contender.name] = Price(price_in or 0.0, price_out or 0.0)

        boards = run(samples, categories, contenders, prices=prices)
        self._report(boards, samples, categories, unpriced)
        if options["csv"]:
            self._write_csv(boards, options["csv"])

    def _report(self, boards, samples, categories, unpriced) -> None:
        multi = sum(1 for sample in samples if len(sample.gold) >= 2)
        empty = sum(1 for sample in samples if not sample.gold)
        sensitive = [c.ref for c in categories if c.sensitive]
        self.stdout.write(self.style.SUCCESS(
            f"\n═══ Intenções: {len(samples)} mensagens rotuladas "
            f"({multi} com 2+ intenções, {empty} sem intenção da lista) ═══"
        ))
        width = max([6, *(len(board.contender) for board in boards)])
        self.stdout.write(
            f"  {'':<{width}} {'conjunto exato':>15} {'2+ exato':>9} {'precisão':>9} {'cobertura':>10} "
            f"{'F1':>5} {'sensíveis':>10} {'p50 ms':>7} {'p95 ms':>7} {'US$/1k':>8} {'falhas':>7}"
        )
        for board in boards:
            precision, recall, f1 = board.micro()
            p50, p95 = board.latency(0.5), board.latency(0.95)
            per_thousand = board.cost_usd / board.total * 1000 if board.total else 0.0
            multi_text = f"{board.multi_exact}/{board.multi_total}" if board.multi_total else "—"
            self.stdout.write(
                f"  {board.contender:<{width}} "
                f"{f'{board.exact}/{board.total} ({board.exact / board.total:.0%})':>15} "
                f"{multi_text:>9} {_pct(precision):>9} {_pct(recall):>10} "
                f"{'—' if f1 is None else f'{f1:.2f}':>5} {_pct(board.recall(sensitive)):>10} "
                f"{f'{p50:.0f}' if p50 is not None else '—':>7} {f'{p95:.0f}' if p95 is not None else '—':>7} "
                f"{per_thousand:>8.4f} {board.errors:>7}"
            )
        self.stdout.write("\nCobertura por intenção (quantas das que existiam cada um achou):")
        self.stdout.write(f"  {'':<{width}} " + " ".join(f"{c.ref[:12]:>12}" for c in categories))
        for board in boards:
            self.stdout.write(
                f"  {board.contender:<{width}} " + " ".join(f"{_pct(board.recall([c.ref])):>12}" for c in categories)
            )
        self.stdout.write(
            "\n'Conjunto exato' = acertou TODAS as intenções da mensagem e nenhuma a mais. 'Sensíveis' = "
            f"cobertura de {', '.join(sensitive) or '—'}: deixar passar custa caro. Precisão = das que "
            "disse, quantas existiam; cobertura = das que existiam, quantas disse."
        )
        for model in unpriced:
            self.stdout.write(self.style.WARNING(
                f"Custo de llm:{model} zerado: modelo fora da tabela; passe --llm-price-in/--llm-price-out."
            ))
        for board in boards:
            failures = [row for row in board.rows if row[4]]
            if failures:
                self.stdout.write(self.style.WARNING(
                    f"{board.contender}: {len(failures)} falhas; a primeira: {failures[0][4]}"
                ))
        self.stdout.write("Nada foi gravado: o piloto só mede.")

    def _write_csv(self, boards, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["concorrente", "amostra", "gabarito", "previsto", "confiancas", "acertou_conjunto", "falha"])
            for board in boards:
                for sample_id, gold, predicted, scores, error in board.rows:
                    writer.writerow([
                        board.contender, sample_id,
                        " ".join(sorted(gold)), " ".join(sorted(predicted)),
                        " ".join(f"{ref}={value:.2f}" for ref, value in sorted(scores.items())),
                        "sim" if (not error and predicted == gold) else "não", error,
                    ])
        self.stdout.write(f"Caso a caso em {path} (sem texto de cliente; leia pela amostra no Admin).")
