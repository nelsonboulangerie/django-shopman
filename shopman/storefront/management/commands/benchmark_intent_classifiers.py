"""Piloto de intenções: regex × embeddings × LLM × Jev contra o gabarito conferido.

Invólucro de ``shopman.storefront.concierge.intent_benchmark``: escolhe
concorrentes, roda, imprime o placar e, com ``--csv``, grava caso a caso
(número da amostra, intenções do gabarito e previstas, confianças) para
calibrar cortes. O CSV não leva texto de cliente: o texto se lê no Admin pela
amostra. Não grava nada no banco — o ciclo automático (``run_intent_pilot``)
é quem guarda o placar no Admin.

LLM e Jev só entram se o provedor deles estiver em
``SHOPMAN_INTENT_PILOT_PROVIDERS_APPROVED``: sem isso, saem do placar dizendo
por quê.
"""

from __future__ import annotations

import csv

from django.core.management.base import BaseCommand, CommandError

from shopman.storefront.concierge.intent_benchmark import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MIN_SIMILARITY,
    build_contenders,
    gold_samples,
    load_categories,
    prices_for,
    render_report,
    run,
)

CONTENDERS = ("regex", "embed", "llm", "jev")


class Command(BaseCommand):
    help = "Mede classificadores de intenção contra as mensagens conferidas no Admin. Não grava nada."

    def add_arguments(self, parser):
        parser.add_argument(
            "--contender", choices=CONTENDERS, action="append",
            help="Concorrente; repetível. Sem --contender, todos (quem não puder rodar fica de fora, com o motivo).",
        )
        parser.add_argument("--limit", type=int, default=500, help="Máximo de amostras conferidas (default 500).")
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
        contenders, skipped = build_contenders(
            requested,
            llm_models=options["llm_model"],
            embedding_model=options["embedding_model"],
            min_similarity=options["min_similarity"],
        )
        for name, reason in skipped:
            if options["contender"]:
                raise CommandError(f"{name}: {reason}")
            self.stdout.write(self.style.WARNING(f"{name}: fora do placar — {reason}"))

        categories = load_categories()
        if not categories:
            raise CommandError("Sem intenções ativas. Rode setup_intent_categories ou crie no Admin.")
        samples = gold_samples(limit=options["limit"])
        if not samples:
            raise CommandError(
                "Gabarito vazio: nenhuma mensagem conferida. Rode sample_intent_messages e confira em "
                "Admin → Clientes → Mensagens para rotular."
            )

        prices, unpriced = prices_for(
            contenders,
            llm_price_in=options["llm_price_in"],
            llm_price_out=options["llm_price_out"],
            jev_price_in=options["jev_price_in"],
        )
        boards = run(samples, categories, contenders, prices=prices)
        self.stdout.write(self.style.SUCCESS("\n═══ Placar das intenções ═══"))
        self.stdout.write(render_report(boards, samples, categories))
        for model in unpriced:
            self.stdout.write(self.style.WARNING(
                f"Custo de llm:{model} zerado: modelo fora da tabela; passe --llm-price-in/--llm-price-out."
            ))
        self.stdout.write("Nada foi gravado: o comando só mede.")
        if options["csv"]:
            self._write_csv(boards, options["csv"])

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
