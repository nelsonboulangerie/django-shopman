"""Placar de conversa sobre as conversas reais: o cliente foi atendido, turno a turno.

    manage.py concierge_conversation_eval                  # últimos 7 dias, canal whatsapp
    manage.py concierge_conversation_eval --days 1 --show 60
    manage.py concierge_conversation_eval --conversation 42
    manage.py concierge_conversation_eval --replay           # as mesmas falas no código de hoje
    manage.py concierge_conversation_eval --replay --paid    # idem, com Jev e modelo (custa)
    manage.py concierge_conversation_eval --replay --framework inform   # idem, com o motor ligado

Só leitura, sem modelo, sem rede. Cada turno sai como útil, sem saída, sem lastro ou
silêncio, com a coluna do ManyChat AI ESTIMADA pela documentação (não medida: o add-on está desligado).
O texto do cliente e da casa sai redigido (documento, telefone, e-mail, endereço omitidos).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from shopman.storefront.concierge import conversation_eval


class Command(BaseCommand):
    help = "Placar de conversa: as conversas reais, turno a turno, e o que a IA do ManyChat faria."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--channel", default="whatsapp")
        parser.add_argument("--conversation", type=int, default=None, help="Só esta conversa (id).")
        parser.add_argument("--show", type=int, default=40, help="Quantos turnos a consertar mostrar.")
        parser.add_argument(
            "--replay", action="store_true",
            help="Refaz as falas reais no código de HOJE, numa transação desfeita, sem enviar nada.",
        )
        parser.add_argument("--paid", action="store_true", help="Com --replay: a IA paga liga (freio de sempre).")
        parser.add_argument(
            "--framework", default="",
            help="Com --replay: classes do motor do framework ligadas só no replay (inform,handoff,order).",
        )

    def handle(self, *args, **options):
        if options["replay"]:
            turns, info = conversation_eval.replay_turns(
                days=options["days"], channel_ref=options["channel"], conversation_id=options["conversation"],
                paid=options["paid"],
                framework=tuple(name for name in options["framework"].split(",") if name),
            )
            self.stdout.write(
                f"Replay no código de hoje ({'IA paga ligada' if info['paid'] else 'sem IA paga'}"
                f"{'; motor do framework: ' + ','.join(info['framework']) if info['framework'] else ''}): "
                f"{info['turns']} turnos de {info['conversations']} conversas; "
                f"{info['skipped']} conversas fora da coorte ficaram de fora. Nada foi enviado nem gravado."
            )
        else:
            turns = conversation_eval.read_turns(
                days=options["days"], channel_ref=options["channel"], conversation_id=options["conversation"]
            )
        self.stdout.write(conversation_eval.render(turns, show=options["show"]))
