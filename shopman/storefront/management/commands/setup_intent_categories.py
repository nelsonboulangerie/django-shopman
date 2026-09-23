"""Cria o vocabulário inicial de intenções do piloto (INTENT-PILOT-PLAN). Idempotente.

A lista é PROPOSTA de partida, não decisão: o dono edita no Admin (Clientes →
Intenções) — nome, descrição, sensível, ativa. Este comando só cria o que falta
pela referência e nunca sobrescreve o que alguém já mudou.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

# (ref, nome, descrição, sensível)
DEFAULT_INTENTS = (
    ("order", "Pedido", "Fazer, alterar ou cancelar um pedido: quer comprar algo agora ou para uma data.", False),
    (
        "product_question", "Dúvida de produto",
        "Pergunta sobre produto: o que tem hoje, sabor, ingrediente, tamanho, preço.", False,
    ),
    (
        "hours_delivery", "Horário, retirada ou entrega",
        "Pergunta sobre horário de funcionamento, endereço, retirada, entrega ou frete.", False,
    ),
    ("order_status", "Status do pedido", "Quer saber de um pedido já feito: se saiu, quando chega, se está pronto.", False),
    ("complaint", "Reclamação", "Reclama de pedido, produto, cobrança, atraso ou atendimento.", True),
    ("allergy", "Alergia ou restrição", "Menciona alergia, intolerância ou restrição alimentar (glúten, lactose, nozes…).", True),
    ("special_order", "Encomenda especial", "Encomenda grande, personalizada ou para evento (festa, casamento, empresa).", False),
    ("human", "Falar com uma pessoa", "Pede para falar com um atendente ou uma pessoa da equipe.", True),
)


class Command(BaseCommand):
    help = "Cria as intenções iniciais do piloto de mensageria (só as que faltam; nunca sobrescreve)."

    def handle(self, *args, **options):
        from shopman.storefront.models import IntentCategory

        created = 0
        for position, (ref, name, description, sensitive) in enumerate(DEFAULT_INTENTS, start=1):
            _obj, was_created = IntentCategory.objects.get_or_create(
                ref=ref,
                defaults={
                    "name": name, "description": description,
                    "sensitive": sensitive, "position": position * 10,
                },
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(
            f"{created} intenção(ões) criada(s); {len(DEFAULT_INTENTS) - created} já existiam. "
            "Edite em Admin → Clientes → Intenções."
        ))
