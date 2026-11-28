"""Placar da resposta às perguntas frequentes: a FAQ direta contra a IA a partir das FAQs (WP-18).

    manage.py concierge_faq_eval --arm faq                                   # de graça
    manage.py concierge_faq_eval --arm model --paid --budget-usd 0.2 --model deepseek-flash

O braço ``model`` chama o provedor pelo propósito ``concierge`` (texto de cliente, só a
conexão liberada para ele) e custa: sem ``--paid`` sai com erro antes de criar cliente. O
gasto passa pelo freio e pelo medidor de produção. Não grava nada além do medidor.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from shopman.storefront.concierge import faq_eval
from shopman.storefront.concierge.reply_eval import Budget


class Command(BaseCommand):
    help = "Mede a resposta às perguntas frequentes: FAQ direta (faq) ou IA a partir das FAQs (model)."

    def add_arguments(self, parser):
        parser.add_argument("--arm", choices=faq_eval.ARMS, default="faq")
        parser.add_argument("--channel", default="whatsapp", help="Canal cujas FAQs valem (default whatsapp).")
        parser.add_argument("--model", default="", help="Com --arm model: o modelo (default: o da rota concierge).")
        parser.add_argument("--paid", action="store_true", help="Autoriza o braço model, que custa.")
        parser.add_argument("--budget-usd", type=float, default=0.2, help="Teto da rodada (default US$ 0,20).")
        parser.add_argument("--show", type=int, default=30, help="Quantos erros e respostas mostrar.")
        parser.add_argument("--golden", default="", help="Outro arquivo de casos.")
        parser.add_argument(
            "--include-drafts",
            action="store_true",
            help="Inclui as perguntas frequentes em rascunho, SÓ no teste (nada é publicado).",
        )
        parser.add_argument(
            "--jev-check",
            action="store_true",
            help="Com --arm model: o Jev confere se cada resposta se sustenta nas FAQs citadas (custa).",
        )

    def handle(self, *args, **options):
        cases = faq_eval.load_golden(options["golden"] or None)
        client = model = None
        budget = None
        if options["arm"] == "model":
            if not options["paid"]:
                raise CommandError(
                    "--arm model chama o provedor e custa dinheiro: rode de novo com --paid (e o teto "
                    "--budget-usd). Nenhuma chamada foi feita."
                )
            from shopman.shop import ai

            try:
                client, route_model = ai.anthropic_client("concierge", timeout=faq_eval.READ_TIMEOUT_S, max_retries=0)
            except ai.AINotConfigured as exc:
                raise CommandError(f"sem conexão de IA para a Concierge: {exc}") from exc
            model = options["model"] or route_model
            try:
                budget = Budget(options["budget_usd"])
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
        report = faq_eval.run(
            cases, arm=options["arm"], channel_ref=options["channel"], client=client, model=model or "", budget=budget,
            include_drafts=options["include_drafts"], jev_check=options["jev_check"],
        )
        self.stdout.write("═══ Perguntas frequentes: FAQ direta × IA a partir das FAQs ═══")
        self.stdout.write(report.render(show=options["show"]))
        if budget is not None:
            self.stdout.write(f"Gasto da rodada: US$ {budget.spent_usd:.4f} de US$ {budget.limit_usd:.4f} (tabela LLM_PRICES).")
        self.stdout.write("Nada foi gravado: o comando só mede.")
