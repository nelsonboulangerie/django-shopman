"""As três chaves legadas mudam de casa, e o sentinela vira proveniência.

A F1 deixou `alergenos`, `dieta` e `porcoes` apontando para as chaves onde os
valores já moravam (`metadata["allergens"]`, `["dietary_info"]`, `["serves"]`),
porque quem as ESCREVE é o Core — o formulário de rótulo do Offerman — e mover
sem tocá-lo deixaria o editor lendo vazio. Este WP toca o Core, então os valores
podem vir para casa.

O que muda aqui:

- os três passam a `storage="attributes"`, com o valor em
  `metadata["attributes"][ref]["value"]`;
- `alergenos` e `dieta` deixam de ser lista de termos livres e ganham **opções
  fechadas** — agora o registro controla a escrita, então prometer a restrição
  deixou de ser promessa vazia;
- `metadata["dietary_auto_filled"]` morre. O que ele dizia ("isto veio da ficha
  técnica, pode sobrescrever") passa a ser a proveniência do próprio valor:
  `source="recipe"` sobrescreve, `source="manual"` bloqueia.

⚠️ **A lista de opções nasce da UNIÃO entre a lista canônica e o que já está
gravado.** Fechar a lista só com a canônica descartaria em silêncio um alérgeno
que a casa cadastrou e que a ANVISA não lista (ou que veio escrito diferente) —
e alérgeno perdido é o pior defeito que este arquivo poderia causar. O que
existe entra; o gestor limpa depois, no Admin, olhando.
"""

from django.db import migrations

#: Alergênicos de declaração obrigatória (ANVISA RDC 26/2015), em pt-BR e no
#: vocabulário que a casa já usa. O gestor edita a lista no Admin — ela é ponto
#: de partida, não camisa de força.
#:
#: ⚠️ ``mostarda`` NÃO está na RDC 26/2015 brasileira, e está aqui de propósito:
#: a casa a declara nos produtos de mercearia, e a lista tem de caber o que a
#: casa declara. Lista canônica que não cabe a realidade vira valor descartado
#: em silêncio — e alérgeno descartado é o pior defeito possível aqui.
ALERGENOS_CANONICOS = [
    "glúten", "crustáceos", "ovos", "peixes", "amendoim", "soja", "leite",
    "castanhas", "amêndoa", "avelã", "castanha-de-caju", "castanha-do-brasil",
    "macadâmia", "nozes", "pecã", "pistache", "gergelim", "mostarda",
    "sulfitos", "látex natural",
]

#: Os termos que a loja mostra hoje como preferência alimentar.
DIETA_CANONICA = [
    "100% vegetal", "vegetariano", "sem glúten", "sem lactose",
]

LEGACY = {
    "alergenos": "allergens",
    "dieta": "dietary_info",
    "porcoes": "serves",
}


def _options(values):
    return [{"value": v, "label": v[:1].upper() + v[1:]} for v in values]


def move_values(apps, schema_editor):
    AttributeDefinition = apps.get_model("shop", "AttributeDefinition")
    Product = apps.get_model("offerman", "Product")

    # 1. Descobrir o que já está gravado, para nenhuma opção se perder.
    observados = {"alergenos": set(), "dieta": set()}
    for metadata in Product.objects.values_list("metadata", flat=True):
        if not isinstance(metadata, dict):
            continue
        for ref, legacy_key in (("alergenos", "allergens"), ("dieta", "dietary_info")):
            raw = metadata.get(legacy_key)
            if isinstance(raw, list):
                observados[ref].update(str(v).strip() for v in raw if str(v).strip())

    canonicas = {"alergenos": ALERGENOS_CANONICOS, "dieta": DIETA_CANONICA}
    for ref in ("alergenos", "dieta"):
        # União preservando a ordem: canônica primeiro, o que sobrou do catálogo
        # depois — assim a lista do Admin abre pelo que a lei nomeia.
        extras = sorted(observados[ref] - set(canonicas[ref]))
        AttributeDefinition.objects.filter(ref=ref).update(
            type="multi_choice",
            options=_options(canonicas[ref] + extras),
            storage="attributes",
        )
    # ⚠️ `porcoes` nasceu na F1 como NÚMERO com unidade "porções", e isso estava
    # errado sobre o que o campo é: no catálogo real ele guarda texto de
    # apresentação — "2 pessoas", "6 fatias grossas", "pote 170 g", "lata 80 g".
    # Com `type="number"` a leitura devolvia None para TODO produto, calada.
    # Ninguém sentiu porque a PDP ainda lia a chave crua; agora que ela lê pelo
    # registro, sentiria — e o rótulo perderia a porção.
    AttributeDefinition.objects.filter(ref="porcoes").update(
        storage="attributes",
        type="text",
        unit="",
        hint="Como a porção é apresentada: “2 pessoas”, “6 fatias grossas”, “pote 170 g”.",
    )

    # 2. Mover o valor de cada produto, carregando a proveniência.
    for product in Product.objects.all().iterator(chunk_size=500):
        metadata = dict(product.metadata or {})
        if not any(k in metadata for k in LEGACY.values()) and "dietary_auto_filled" not in metadata:
            continue

        # O sentinela ausente contava como "pode sobrescrever" — mesma leitura
        # que `_is_auto_filled` fazia. True → veio da ficha; False → foi gente.
        from_recipe = bool(metadata.pop("dietary_auto_filled", True))
        root = dict(metadata.get("attributes") or {})

        for ref, legacy_key in LEGACY.items():
            if legacy_key not in metadata:
                continue
            value = metadata.pop(legacy_key)
            if value in (None, "", []):
                continue
            # `porcoes` nunca teve sentinela: valor que está lá foi digitado.
            source = "recipe" if (from_recipe and ref != "porcoes") else "manual"
            root[ref] = {
                "value": value,
                "source": source,
                "reviewed": source == "manual",
            }

        if root:
            metadata["attributes"] = root
        else:
            metadata.pop("attributes", None)

        product.metadata = metadata
        product.save(update_fields=["metadata"])


def restore_values(apps, schema_editor):
    AttributeDefinition = apps.get_model("shop", "AttributeDefinition")
    Product = apps.get_model("offerman", "Product")

    for ref, legacy_key in LEGACY.items():
        AttributeDefinition.objects.filter(ref=ref).update(storage=f"metadata:{legacy_key}")
    AttributeDefinition.objects.filter(ref__in=("alergenos", "dieta")).update(
        type="multi_text", options=[],
    )
    AttributeDefinition.objects.filter(ref="porcoes").update(type="number", unit="porções")

    for product in Product.objects.all().iterator(chunk_size=500):
        metadata = dict(product.metadata or {})
        root = dict(metadata.get("attributes") or {})
        if not root:
            continue
        touched = False
        for ref, legacy_key in LEGACY.items():
            record = root.get(ref)
            if not isinstance(record, dict) or "value" not in record:
                continue
            metadata[legacy_key] = record["value"]
            if ref == "dieta":
                metadata["dietary_auto_filled"] = record.get("source") == "recipe"
            root.pop(ref, None)
            touched = True
        if not touched:
            continue
        if root:
            metadata["attributes"] = root
        else:
            metadata.pop("attributes", None)
        product.metadata = metadata
        product.save(update_fields=["metadata"])


def forget_caches(apps, schema_editor):
    from shopman.shop.services.attributes import invalidate_cache

    invalidate_cache()


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0032_forget_rules_cache"),
        ("offerman", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(move_values, restore_values),
        # A definição mudou de tipo e de storage: o registro em cache mentiria
        # até o TTL, e o motor leria o valor do lugar errado.
        migrations.RunPython(forget_caches, forget_caches),
    ]
