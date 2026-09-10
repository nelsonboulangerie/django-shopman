"""
Management command: waitlist_report

Retrato da fila de espera viva, por SKU e em ordem FCFS (WP-P2E F3).

O selo do board conta um pedido de cada vez. Esta é a pergunta do outro lado,
a de quem decide a produção: quanta gente está esperando este item, há quanto
tempo, e para qual fornada. É o número que responde "vale abrir uma fornada
extra?" e "posso pôr esta vaga na gôndola sem furar a fila?".

Usage::

    python manage.py waitlist_report
    python manage.py waitlist_report --json
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Mostra a fila de espera viva por SKU (ordem FCFS)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        from shopman.shop.services import waitlist

        rows = waitlist.report()
        if options.get("as_json"):
            self.stdout.write(json.dumps(rows, ensure_ascii=False, indent=2))
            return None

        if not rows:
            self.stdout.write("Nenhum pedido na fila de espera.")
            return None

        for row in rows:
            self.stdout.write(
                f"\n{row['sku']} — {row['waiting']} na fila, {row['qty_reserved']} un. reservadas"
            )
            for entry in row["queue"]:
                self.stdout.write(
                    f"  {entry['position']:>2}. {entry['order_ref']:<16} "
                    f"{entry['state']:<11} {entry['qty']:>4} un. "
                    f"fornada={entry['batch_date'] or '?'} "
                    f"esperando há {entry['waiting_minutes']} min"
                )
        return None
