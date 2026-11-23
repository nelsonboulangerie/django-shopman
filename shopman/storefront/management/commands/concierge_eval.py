"""O ensaio do leitor da Nice no ar: ``manage.py concierge_eval --battery``.

Roda a bateria de 56 pedidos pelo leitor de verdade (o portão do Jev e a IA da rota ``intents``,
pelo freio e pelo medidor de gasto da casa) e imprime o placar e a transcrição. Nenhum efeito,
nenhuma mensagem, nenhuma linha nova no banco: a conversa e a sacola são de memória
(``concierge/eval_battery.py``). Tem teto de chamadas próprio (``--max-calls``), além do freio.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Ensaio do leitor da Nice: a bateria de pedidos pela IA do perfil, sem efeito e sem escrita."

    def add_arguments(self, parser):
        parser.add_argument("--battery", action="store_true", help="roda a bateria de 56 pedidos")
        parser.add_argument("--max-calls", type=int, default=150, help="teto de chamadas à IA (padrão 150)")
        parser.add_argument("--max-usd", type=float, default=0.50,
                            help="teto de custo estimado, em dólares (padrão 0,50)")
        parser.add_argument("--case", default="", help="só os casos cujo id contém este texto")
        parser.add_argument("--channel", default="whatsapp", help="o canal cujo cardápio a leitura usa")

    def handle(self, *args, **options):
        from shopman.storefront.concierge import eval_battery
        from shopman.storefront.concierge.model_reader import NiceReader, build_client

        if not options["battery"]:
            raise CommandError("diga o que rodar: --battery")
        if options["max_calls"] < 1 or options["max_usd"] <= 0:
            raise CommandError("--max-calls precisa ser ao menos 1 e --max-usd maior que zero")
        client, model = build_client()
        if client is None:
            raise CommandError("a rota de IA 'intents' não tem conexão utilizável (Admin, conexões de IA), "
                               "ou o freio de gasto está puxado: nada foi chamado")

        def reader_for(conversation, lines_of):
            return NiceReader(client=client, model=model, conversation=conversation, lines_of=lines_of)

        resultados, totais = eval_battery.rodar(reader_for, channel_ref=options["channel"],
                                                today=timezone.localdate(), max_calls=options["max_calls"],
                                                max_usd=options["max_usd"], model=model, only=options["case"])
        self.stdout.write(eval_battery.relatorio(resultados, totais))
        # Teto estourado ou IA que recusou: o placar não mede o leitor, e o comando sai com erro.
        if totais["interrompido"]:
            raise CommandError(f"ensaio interrompido: {totais['interrompido']}")
        if totais["erros"]:
            raise CommandError(f"a IA recusou {len(totais['erros'])} falas; a primeira: {totais['erros'][0]}")
