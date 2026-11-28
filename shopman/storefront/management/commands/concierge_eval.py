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
        parser.add_argument("--cards", action="store_true", help="roda os 5 cartões pelo motor, em memória")
        parser.add_argument("--max-calls", type=int, default=150, help="teto de chamadas à IA (padrão 150)")
        parser.add_argument("--max-usd", type=float, default=0.50,
                            help="teto de custo estimado, em dólares (padrão 0,50)")
        parser.add_argument("--case", default="", help="só os casos cujo id contém este texto")
        parser.add_argument("--channel", default="whatsapp", help="o canal cujo cardápio a leitura usa")
        parser.add_argument("--classes", default="",
                            help="as classes ligadas para o juiz dos cartões, separadas por vírgula "
                                 "(ex.: inform,order); sem ela, todas")

    def handle(self, *args, **options):
        from shopman.storefront.concierge import eval_battery
        from shopman.storefront.concierge.model_reader import NiceReader, build_client

        if not (options["battery"] or options["cards"]):
            raise CommandError("diga o que rodar: --battery, --cards ou os dois")
        from shopman.storefront.concierge.turn_framework import ACTION_CLASSES

        classes = frozenset(name.strip() for name in options["classes"].split(",") if name.strip()) or None
        if classes is not None and classes - set(ACTION_CLASSES):
            raise CommandError(f"classe desconhecida: {', '.join(sorted(classes - set(ACTION_CLASSES)))}; "
                               f"as classes são {', '.join(sorted(ACTION_CLASSES))}")
        if options["max_calls"] < 1 or options["max_usd"] <= 0:
            raise CommandError("--max-calls precisa ser ao menos 1 e --max-usd maior que zero")
        client, model = build_client()
        if client is None:
            raise CommandError("a rota de IA 'intents' não tem conexão utilizável (Admin, conexões de IA), "
                               "ou o freio de gasto está puxado: nada foi chamado")

        def reader_for(conversation, lines_of):
            return NiceReader(client=client, model=model, conversation=conversation, lines_of=lines_of)

        today = timezone.localdate()
        problemas: list[str] = []
        restam = {"calls": options["max_calls"], "usd": options["max_usd"]}
        if options["battery"]:
            resultados, totais = eval_battery.rodar(reader_for, channel_ref=options["channel"], today=today,
                                                    max_calls=restam["calls"], max_usd=restam["usd"], model=model,
                                                    only=options["case"])
            self.stdout.write(eval_battery.relatorio(resultados, totais))
            problemas += self._problemas(totais)
            restam = {"calls": restam["calls"] - totais["chamadas"], "usd": restam["usd"] - totais["usd"]}
        if options["cards"] and not problemas:
            from shopman.storefront.concierge import eval_cards

            if options["battery"]:
                self.stdout.write("")
            placares, totais = eval_cards.rodar(reader_for, today=today, max_calls=max(restam["calls"], 0),
                                                max_usd=max(restam["usd"], 1e-9), model=model, only=options["case"],
                                                classes=classes)
            self.stdout.write(eval_cards.relatorio(placares, totais))
            problemas += self._problemas(totais)
        # Teto estourado ou IA que recusou: o placar não mede o leitor, e o comando sai com erro.
        if problemas:
            raise CommandError("; ".join(problemas))

    @staticmethod
    def _problemas(totais) -> list[str]:
        found = []
        if totais["interrompido"]:
            found.append(f"ensaio interrompido: {totais['interrompido']}")
        if totais["erros"]:
            found.append(f"a IA recusou {len(totais['erros'])} falas; a primeira: {totais['erros'][0]}")
        return found
