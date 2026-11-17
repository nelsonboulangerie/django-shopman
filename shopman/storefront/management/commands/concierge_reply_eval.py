"""Placar da Concierge contra o conjunto de mensagens reais (golden set).

Invólucro de ``shopman.storefront.concierge.reply_eval``. Sem argumentos, mede o
caminho de hoje com a regra local, sem rede e sem custo. ``--classifier model``
ou ``jev`` chama o provedor de verdade com o texto redigido do caso e imprime o
custo e o tempo medidos pela régua. ``--production`` resume o que a régua gravou
nas respostas reais. ``--memory`` mede a memória da conversa (OBS0310-N) nos casos
que dependem do contexto, antes e depois. Não grava nada no banco.

Rodada com rede custa dinheiro (``--classifier model``, ``--classifier jev``,
``--plural --reader model``): sem ``--paid`` o comando sai com erro antes de criar
qualquer cliente. Com ``--paid``, ``--budget-usd`` (default US$ 1) é o teto de gasto
da rodada inteira, pelo custo de ``LLM_PRICES``, e ``--max-cases`` limita os casos
medidos em cada repetição. Modelo fora da tabela para a rodada: o teto não contém o
que não sabe contar.

``--repeat N`` roda N vezes os mesmos casos e mostra cada medida também "em todas as
N". ``--report <arquivo>`` grava o placar em Markdown.
"""

from __future__ import annotations

import pathlib
import shlex
import sys

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from shopman.utils.formatting import format_clock

from shopman.storefront.concierge.reply_eval import (
    CLASSIFIERS,
    READERS,
    Budget,
    consistency,
    house_rules_summary,
    load_golden,
    network_reason,
    production_summary,
    run,
    run_plural,
)

NOTHING_SAVED = "Nada foi gravado: o comando só mede."


class Command(BaseCommand):
    help = "Mede a Concierge de hoje contra as mensagens reais conferidas (golden set). Não grava nada."

    def add_arguments(self, parser):
        parser.add_argument(
            "--classifier",
            choices=CLASSIFIERS,
            default="rules",
            help=(
                "Quem propõe a intenção na triagem: rules (padrão, sem rede), model (Anthropic; custa, pede --paid), "
                "jev (custa, pede --paid), ou jev-shadow (a intenção que o Jev deu em sombra no alpha, gravada no "
                "caso; sem rede)."
            ),
        )
        parser.add_argument(
            "--model", default="", help="Modelo da triagem com --classifier model (default: o da rota de IA triage)."
        )
        parser.add_argument("--golden", default="", help="Outro arquivo de casos (default: concierge/golden_set.json).")
        parser.add_argument("--limit", type=int, default=0, help="Só os N primeiros casos.")
        parser.add_argument("--show-misses", type=int, default=15, help="Quantos erros listar (default 15).")
        parser.add_argument(
            "--plural",
            action="store_true",
            help="Mede as intenções no plural (OBS0310-Q): partes achadas antes (uma intenção) e depois.",
        )
        parser.add_argument(
            "--reader",
            choices=READERS,
            default="local",
            help="Com --plural: local (divisão local, sem rede) ou model (leitura com o modelo pequeno; custa, pede --paid).",
        )
        parser.add_argument("--production", action="store_true", help="Resume a régua gravada nas respostas reais.")
        parser.add_argument("--days", type=int, default=7, help="Janela do --production, em dias (default 7).")
        parser.add_argument(
            "--memory",
            action="store_true",
            help="Mede a memória da conversa nos casos que dependem do contexto (golden_memory.json), antes e depois.",
        )
        parser.add_argument(
            "--paid",
            action="store_true",
            help="Autoriza a rodada com rede (que custa). Sem ele, leitor ou classificador de rede sai com erro.",
        )
        parser.add_argument(
            "--budget-usd",
            type=float,
            default=1.0,
            help="Com --paid: teto de gasto da rodada inteira, todas as repetições (default US$ 1, tabela LLM_PRICES).",
        )
        parser.add_argument(
            "--max-cases",
            type=int,
            default=0,
            help="Para cada repetição depois de N casos medidos (default 0 = todos).",
        )
        parser.add_argument(
            "--repeat",
            type=int,
            default=1,
            help='Roda N vezes os mesmos casos e mostra cada medida também "em todas as N" (default 1).',
        )
        parser.add_argument("--report", default="", help="Grava o placar em Markdown neste arquivo.")

    def handle(self, *args, **options):
        repeat = options["repeat"]
        if repeat < 1:
            raise CommandError("--repeat precisa ser 1 ou mais.")
        if options["max_cases"] < 0:
            raise CommandError("--max-cases não pode ser negativo.")
        paid_by = network_reason(classifier=options["classifier"], plural=options["plural"], reader=options["reader"])
        if options["memory"] or options["production"]:
            paid_by = ""
            if repeat > 1:
                raise CommandError(
                    "--repeat mede o placar da triagem e o das partes; --memory e --production não variam."
                )
        if paid_by and not options["paid"]:
            # Antes de qualquer cliente: rodada com rede custa, e custo pede a palavra de quem roda.
            raise CommandError(
                f"{paid_by} chama o provedor e custa dinheiro: rode de novo com --paid (e o teto --budget-usd, "
                "default US$ 1) para autorizar o gasto. Nenhuma chamada foi feita."
            )
        budget = None
        if paid_by:
            try:
                budget = Budget(options["budget_usd"])
            except ValueError as exc:
                raise CommandError(str(exc)) from exc

        text = self._measure(options, repeat=repeat, budget=budget)
        if budget is not None:
            text += f"\nGasto da rodada: US$ {budget.spent_usd:.4f} de US$ {budget.limit_usd:.4f} (tabela LLM_PRICES)."
        self.stdout.write(text)
        self.stdout.write(NOTHING_SAVED)
        if options["report"]:
            path = pathlib.Path(options["report"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_markdown(text), encoding="utf-8")
            self.stdout.write(f"Placar gravado em {path}.")

    def _measure(self, options, *, repeat: int, budget) -> str:
        if options["production"]:
            return production_summary(days=options["days"])
        cases = load_golden(options["golden"] or None)
        if options["limit"]:
            cases = cases[: options["limit"]]
        if not cases:
            raise CommandError("Conjunto vazio.")
        if options["memory"]:
            from shopman.storefront.concierge import dialogue_eval

            return "\n".join(
                [
                    "═══ Placar da memória da Concierge (golden set) ═══",
                    dialogue_eval.render(dialogue_eval.run(cases), show_misses=options["show_misses"]),
                ]
            )
        reports = []
        try:
            for _ in range(repeat):
                if options["plural"]:
                    report = run_plural(
                        cases,
                        reader=options["reader"],
                        budget=budget,
                        max_cases=options["max_cases"],
                    )
                else:
                    report = run(
                        cases,
                        classifier=options["classifier"],
                        model=options["model"],
                        budget=budget,
                        max_cases=options["max_cases"],
                    )
                reports.append(report)
                if budget is not None and budget.stop_reason(measured=0, total=0):
                    break  # o teto vale para a rodada inteira: as repetições seguintes não começam
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        first = reports[0]
        if options["plural"]:
            lines = ["═══ Intenções no plural (golden set) ═══", first.render(show_misses=options["show_misses"])]
        else:
            lines = [
                "═══ Placar da Concierge (golden set) ═══",
                first.render(show_misses=options["show_misses"]),
                house_rules_summary(cases),
            ]
        if repeat > 1:
            if len(reports) < repeat:
                lines.append(f"\n⚠ Só {len(reports)} de {repeat} rodadas: o teto de gasto parou a repetição.")
            lines.append("")
            lines.append(consistency(reports) if len(reports) > 1 else "Repetição: uma rodada só, nada a comparar.")
        return "\n".join(lines)


def _markdown(text: str) -> str:
    command = "manage.py concierge_reply_eval " + " ".join(shlex.quote(arg) for arg in _argv())
    return (
        "# Placar da Concierge\n\n"
        f"- Comando: `{command.strip()}`\n"
        f"- Medido em: {timezone.localtime():%d/%m/%Y} {format_clock(timezone.localtime())}\n\n"
        "```text\n" + text.rstrip() + "\n```\n"
    )


def _argv() -> list[str]:
    """Os argumentos da linha de comando, sem o ``--report`` (o arquivo é este)."""
    argv = list(sys.argv)
    if "concierge_reply_eval" not in argv:
        return []
    args, skip = [], False
    for arg in argv[argv.index("concierge_reply_eval") + 1 :]:
        if skip:
            skip = False
        elif arg == "--report":
            skip = True
        elif not arg.startswith("--report="):
            args.append(arg)
    return args
