"""Absorção: cada Showcase passa a existir também como Channel `display`.

Expand, ainda não contract. Esta migração **cria** a representação nova e não
remove nada: o `Showcase` continua existindo e continua sendo quem os
renderizadores e a matriz leem. A troca de leitor e a remoção do model vêm na F4,
depois de verificar que as duas representações dizem a mesma coisa.

Por que canal e não entidade própria: exibir catálogo com preço responde à mesma
pergunta que vender — o que difere não é a natureza da superfície, é até onde a
interação comercial vai nela. Duas entidades para uma pergunta produziam
maquinaria duplicada (dois construtores de superfície na matriz, dois caminhos de
service, dois admins) em volta de uma diferença que cabe num discriminador
(ADR-018 §1).

Mapeamentos:

- `kind` → `config.display.format`. `menuboard` vira **vazio**, porque menuboard é
  *rota*, não dialeto: `/menuboard/<ref>/` renderiza HTML+SSE e `/feed/<ref>.xml`
  renderiza XML. Ao `format` resta dizer se o XML segue Google Merchant ou Meta.
- `collections` e `options["paused_skus"]` → `config.display`, sem tradução.
- `options["short_name"]` → `config.short_name`, que já existia no ChannelConfig.
- `prices_from` → o canal transacional cujo preço este canal anuncia:
  · **feed** aponta para a loja, porque o feed manda o cliente para a loja e o
    Merchant Center exige que o preço case com a landing page;
  · **menuboard** aponta para o PDV, porque a TV está fisicamente na loja e tem de
    concordar com o balcão (decisão do dono).

`display_order` continua depois dos canais transacionais, para o canal de exibição
nunca aparecer antes de um canal de venda em nenhuma lista ordenada.

Refs ADR-018 §1 e §5, plano F3b (passo 3).
"""

from __future__ import annotations

from django.conf import settings
from django.db import migrations

FORMAT_BY_KIND = {
    "menuboard": "",  # rota, não dialeto
    "google": "google_merchant",
    "meta": "meta_catalog",
}


def forward(apps, schema_editor):
    Showcase = apps.get_model("shop", "Showcase")
    Channel = apps.get_model("shop", "Channel")

    storefront_ref = getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web")
    pos_ref = getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "pdv")

    # Canal de exibição nunca vem antes de canal de venda em lista ordenada.
    last_order = (
        Channel.objects.order_by("-display_order")
        .values_list("display_order", flat=True)
        .first()
        or 0
    )

    for offset, showcase in enumerate(Showcase.objects.all().order_by("name"), start=1):
        options = showcase.options or {}
        kind = showcase.kind or "menuboard"
        is_feed = kind in ("google", "meta")

        display = {
            "format": FORMAT_BY_KIND.get(kind, ""),
            "collections": list(showcase.collections or []),
            "prices_from": storefront_ref if is_feed else pos_ref,
            "paused_skus": list(options.get("paused_skus") or []),
        }
        config = {"display": display}
        short_name = (options.get("short_name") or "").strip()
        if short_name:
            config["short_name"] = short_name

        channel, created = Channel.objects.get_or_create(
            ref=showcase.ref,
            defaults={
                "name": showcase.name or showcase.ref,
                "commerce_policy": "display",
                "is_active": showcase.is_active,
                "display_order": last_order + offset,
                "config": config,
            },
        )
        if created:
            continue

        # Canal preexistente com a mesma ref: preenche o que falta sem sobrescrever
        # o que alguém já configurou à mão.
        channel.commerce_policy = "display"
        merged = dict(channel.config or {})
        merged.setdefault("display", {})
        for key, value in display.items():
            merged["display"].setdefault(key, value)
        if short_name:
            merged.setdefault("short_name", short_name)
        channel.config = merged
        channel.save(update_fields=["commerce_policy", "config"])


def backward(apps, schema_editor):
    """Remove só os canais que esta migração criou — os que espelham um Showcase."""
    Showcase = apps.get_model("shop", "Showcase")
    Channel = apps.get_model("shop", "Channel")

    refs = list(Showcase.objects.values_list("ref", flat=True))
    Channel.objects.filter(ref__in=refs, commerce_policy="display").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0033_channel_commerce_policy"),
    ]

    operations = [migrations.RunPython(forward, backward)]
