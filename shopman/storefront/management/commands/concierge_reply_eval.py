"""Placar da Concierge contra o conjunto de mensagens reais (golden set).

Invólucro de ``shopman.storefront.concierge.reply_eval``. Sem argumentos, mede o
caminho de hoje com a regra local, sem rede e sem custo. ``--classifier model``
ou ``jev`` chama o provedor de verdade com o texto redigido do caso e imprime o
custo e o tempo medidos pela régua. ``--production`` resume o que a régua gravou
nas respostas reais. ``--memory`` mede a memória da conversa (OBS0310-N) nos casos
que dependem do contexto, antes e depois. Não grava nada.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from shopman.storefront.concierge.reply_eval import CLASSIFIERS, load_golden, production_summary, run


class Command(BaseCommand):
    help = "Mede a Concierge de hoje contra as mensagens reais conferidas (golden set). Não grava nada."

    def add_arguments(self, parser):
        parser.add_argument(
            "--classifier", choices=CLASSIFIERS, default="rules",
            help=(
                "Quem propõe a intenção na triagem: rules (padrão, sem rede), model (Anthropic), jev, ou "
                "jev-shadow (a intenção que o Jev deu em sombra no alpha, gravada no caso; sem rede)."
            ),
        )
        parser.add_argument("--model", default="", help="Modelo da triagem com --classifier model (default: o do settings).")
        parser.add_argument("--golden", default="", help="Outro arquivo de casos (default: concierge/golden_set.json).")
        parser.add_argument("--limit", type=int, default=0, help="Só os N primeiros casos.")
        parser.add_argument("--show-misses", type=int, default=15, help="Quantos erros listar (default 15).")
        parser.add_argument("--production", action="store_true", help="Resume a régua gravada nas respostas reais.")
        parser.add_argument("--days", type=int, default=7, help="Janela do --production, em dias (default 7).")
        parser.add_argument(
            "--memory", action="store_true",
            help="Mede a memória da conversa nos casos que dependem do contexto (golden_memory.json), antes e depois.",
        )

    def handle(self, *args, **options):
        if options["production"]:
            self.stdout.write(production_summary(days=options["days"]))
            return
        cases = load_golden(options["golden"] or None)
        if options["limit"]:
            cases = cases[: options["limit"]]
        if not cases:
            raise CommandError("Conjunto vazio.")
        if options["memory"]:
            from shopman.storefront.concierge import dialogue_eval

            self.stdout.write(self.style.SUCCESS("═══ Placar da memória da Concierge (golden set) ═══"))
            self.stdout.write(dialogue_eval.render(dialogue_eval.run(cases), show_misses=options["show_misses"]))
            self.stdout.write("Nada foi gravado: o comando só mede.")
            return
        try:
            report = run(cases, classifier=options["classifier"], model=options["model"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("═══ Placar da Concierge (golden set) ═══"))
        self.stdout.write(report.render(show_misses=options["show_misses"]))
        self.stdout.write("Nada foi gravado: o comando só mede.")
