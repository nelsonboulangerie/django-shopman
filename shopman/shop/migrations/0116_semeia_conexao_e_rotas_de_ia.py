"""As conexões ``anthropic`` e ``jev`` (sem chave) e as rotas com os modelos que valiam por env.

Até 12/11/2026 o modelo vinha de ``AI_ASSIST_MODEL`` (Opus 5), ``CONCIERGE_MODEL``
(Sonnet 5, também a triagem) e ``CONCIERGE_INTENTS_MODEL`` (Haiku 4.5). As rotas
repetem esses valores para o custo não mudar com a troca. A chave não vem: a
anterior foi desativada no Console em 11/11/2026, e a nova se cola no Admin.
A conexão nasce liberada para mensagem de cliente porque a Anthropic já era o
provedor aprovado pelo dono para isso (23/09/2026).
"""

from django.db import migrations

ROUTES = {
    "default": {"connection": "anthropic"},
    "concierge": {"connection": "anthropic", "model": "claude-sonnet-5"},
    "triage": {"connection": "anthropic", "model": "claude-sonnet-5"},
    "intents": {"connection": "anthropic", "model": "claude-haiku-4-5"},
}


def seed(apps, schema_editor):
    AIConnection = apps.get_model("shop", "AIConnection")
    Shop = apps.get_model("shop", "Shop")
    AIConnection.objects.get_or_create(
        ref="anthropic",
        defaults={
            "name": "Anthropic",
            "protocol": "anthropic",
            "model": "claude-opus-5",
            "price_input_per_m": 5,
            "price_output_per_m": 25,
            "customer_text_approved": True,
        },
    )
    # Jev (TypeSafe), aprovado pelo dono em 02/10/2026 (D-028), inclusive para texto
    # redigido de cliente. Saída grátis; entrada a US$ 0,042 por milhão.
    AIConnection.objects.get_or_create(
        ref="jev",
        defaults={
            "name": "Jev (TypeSafe)",
            "protocol": "jev",
            "model": "jev-latest",
            "price_input_per_m": "0.042",
            "price_output_per_m": 0,
            "customer_text_approved": True,
        },
    )
    for shop in Shop.objects.all():
        if not shop.ai_routes:
            shop.ai_routes = ROUTES
            shop.save(update_fields=["ai_routes"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0115_conexao_de_ia")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
