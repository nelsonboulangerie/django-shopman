"""Grupos do cliente viram N:N e ganham vantagens tipadas.

`Customer.price_tier` era FK única. A frente §7.1 decidiu que o cliente pode pertencer a
mais de um grupo e receber a melhor vantagem por tipo, sem acumular (14/10/2026). A FK dá
lugar ao M2M `price_tiers`, e cada vínculo existente é COPIADO antes da FK sair: sem o
RunPython, todo cliente voltaria a ficar sem grupo e cairia no preço de varejo calado.

`PriceTierAdvantage` nasce vazio: as vantagens tipadas que ele guarda (frete grátis,
coleções e notificações exclusivas) ainda não existiam em nenhum formato anterior.
"""

import django.db.models.deletion
from django.db import migrations, models


def copy_price_tiers(apps, schema_editor):
    Customer = apps.get_model("guestman", "Customer")
    Through = Customer.price_tiers.through
    rows = (
        Customer.objects.exclude(price_tier_id=None)
        .values_list("id", "price_tier_id")
    )
    Through.objects.bulk_create(
        [Through(customer_id=cid, pricetier_id=tid) for cid, tid in rows],
        ignore_conflicts=True,
    )


def restore_price_tier(apps, schema_editor):
    Customer = apps.get_model("guestman", "Customer")
    for customer in Customer.objects.prefetch_related("price_tiers"):
        tier = customer.price_tiers.order_by("-priority", "name").first()
        if tier is not None and customer.price_tier_id != tier.pk:
            customer.price_tier_id = tier.pk
            customer.save(update_fields=["price_tier"])


class Migration(migrations.Migration):

    dependencies = [
        ("guestman", "0005_providererasuretombstone"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="price_tiers",
            field=models.ManyToManyField(
                blank=True,
                related_name="customers",
                to="guestman.pricetier",
                verbose_name="grupos",
            ),
        ),
        migrations.CreateModel(
            name="PriceTierAdvantage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("free_shipping", "Frete grátis"), ("exclusive_collections", "Coleções exclusivas"), ("exclusive_notifications", "Notificações exclusivas")], max_length=32, verbose_name="tipo")),
                ("priority", models.IntegerField(default=0, help_text="Maior vence quando dois grupos do mesmo cliente dão a mesma vantagem.", verbose_name="prioridade")),
                ("is_active", models.BooleanField(default=True, verbose_name="ativa")),
                ("config", models.JSONField(blank=True, default=dict, help_text="Chaves por tipo, documentadas em docs/reference/data-schemas.md.", verbose_name="configuração")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criada em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizada em")),
                ("tier", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="advantages", to="guestman.pricetier", verbose_name="grupo")),
            ],
            options={
                "verbose_name": "vantagem do grupo",
                "verbose_name_plural": "vantagens do grupo",
                "ordering": ["tier", "-priority", "kind"],
                "constraints": [models.UniqueConstraint(fields=("tier", "kind"), name="guestman_price_tier_advantage_uq")],
            },
        ),
        migrations.RunPython(copy_price_tiers, restore_price_tier),
        migrations.RemoveField(
            model_name="customer",
            name="price_tier",
        ),
    ]
