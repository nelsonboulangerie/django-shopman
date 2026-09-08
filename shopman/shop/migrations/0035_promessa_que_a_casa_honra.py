"""Completa o vocabulário de alérgeno e APAGA a promessa que a casa não honra.

Duas correções que precisam vir juntas, porque a segunda depende da primeira
estar no lugar para não voltar no próximo `save` da ficha.

## 1. O vocabulário estava incompleto

A ``0033`` gravou 20 termos. Faltavam:

- **os cereais que a RDC 26/2015 NOMEIA um a um** — ``trigo``, ``centeio``,
  ``cevada``, ``aveia``. Numa padaria é aqui que a declaração vive: "glúten"
  sozinho não distingue um pão de centeio de um pão de trigo, e quem evita
  trigo não evita os dois;
- **``pinoli``**, que a norma nomeia e ficou de fora por descuido de
  transcrição;
- **``pimenta-do-reino``**, que nenhuma norma lista e a casa declara — decisão
  do dono em 06/09/2026, porque já houve reação a ela aqui. O rótulo existe
  para proteger quem come, não para cumprir a lista mínima.

⚠️ Esta migração **não edita a 0033** — ela já rodou no alpha, e migração
aplicada não reexecuta. Acrescenta por cima, preservando o que estiver lá.

## 2. A casa estava prometendo o que não pode cumprir

O ``dietary_from_recipe`` derivava ``sem glúten``, ``sem lactose`` e
``vegetariano`` da ficha. Medido no cardápio vivo em 06/09, **11 produtos
carregavam essas afirmações** — entre eles um Espresso "sem glúten" e nove pães
"sem lactose".

Era verdade sobre a RECEITA e mentira sobre o PRODUTO: farinha no ar, forno e
bancada compartilhados. Afirmação de ausência é a única da família que um
celíaco pode agir em cima, e é justamente a que uma padaria não consegue honrar.

Trocar a derivação não basta: o valor **já gravado** continua no produto até
algo re-derivar. Esta migração limpa o que ficou, e limpa **só o derivado** —
se alguém escreveu à mão (``source="manual"``), a escolha é dele e permanece.

Reversão devolve as opções antigas de ``dieta``, mas **não** ressuscita as
afirmações apagadas: republicar promessa que a casa não honra não é rollback,
é reintroduzir o defeito.
"""

from django.db import migrations

#: A lista COMPLETA, na ordem canônica — copiada, não importada.
#:
#: ⚠️ Migração não importa `attribute_defaults`: ela representa um momento do
#: banco e não pode mudar de sentido quando o código muda. É a mesma razão pela
#: qual a 0033 carrega a própria cópia, e o que
#: `test_the_migration_and_the_defaults_agree` guarda.
ALERGENOS_COMPLETOS = [
    # Os cereais que contêm glúten, NOMEADOS (RDC 26/2015 os nomeia um a um).
    "glúten", "trigo", "centeio", "cevada", "aveia",
    "crustáceos", "ovos", "peixes", "amendoim", "soja", "leite",
    # As castanhas que a norma nomeia — `pinoli` faltava por descuido.
    "castanhas", "amêndoa", "avelã", "castanha-de-caju", "castanha-do-brasil",
    "macadâmia", "nozes", "pecã", "pistache", "pinoli",
    "gergelim", "sulfitos", "látex natural",
    "mostarda",           # obrigatório na UE, não na RDC; a casa declara
    "pimenta-do-reino",   # nenhuma norma lista; decisão do dono (06/09/2026)
]

#: O que a casa deixou de afirmar. `100% vegetal` FICA: é afirmação positiva
#: sobre o que o produto é, não sobre o que falta nele — e essa a ficha honra.
AFIRMACOES_RETIRADAS = {"sem glúten", "sem lactose", "vegetariano"}

DIETA_ANTIGA = ["100% vegetal", "vegetariano", "sem glúten", "sem lactose"]
DIETA_NOVA = ["100% vegetal"]


def _opcoes(valores):
    return [{"value": v, "label": v[:1].upper() + v[1:]} for v in valores]


def completa_e_limpa(apps, schema_editor):
    AttributeDefinition = apps.get_model("shop", "AttributeDefinition")
    Product = apps.get_model("offerman", "Product")

    # ── vocabulário de alérgeno: acrescenta sem apagar o que já existe ──
    d = AttributeDefinition.objects.filter(ref="alergenos").first()
    if d is not None:
        # Reconstrói na ordem canônica e PRESERVA o que o catálogo trouxe de
        # fora dela — a 0033 já guardava esses extras, e apagá-los aqui seria
        # descartar alérgeno declarado por alguém, que é o defeito a evitar.
        atuais = [o.get("value") for o in (d.options or []) if isinstance(o, dict)]
        extras = [v for v in atuais if v and v not in ALERGENOS_COMPLETOS]
        d.options = _opcoes(ALERGENOS_COMPLETOS + extras)
        d.save(update_fields=["options"])

    # ── dieta: um termo só ──
    dd = AttributeDefinition.objects.filter(ref="dieta").first()
    if dd is not None:
        dd.options = _opcoes(DIETA_NOVA)
        dd.save(update_fields=["options"])

    # ── apaga a promessa já gravada, e SÓ a derivada ──
    for produto in Product.objects.all().iterator():
        meta = produto.metadata or {}
        attrs = meta.get("attributes")
        if not isinstance(attrs, dict):
            continue
        campo = attrs.get("dieta")
        if not isinstance(campo, dict):
            continue
        # Escrita à mão é escolha de gente: não se apaga por migração.
        if str(campo.get("source") or "") == "manual":
            continue
        valores = campo.get("value")
        if not isinstance(valores, list):
            continue
        limpos = [v for v in valores if str(v) not in AFIRMACOES_RETIRADAS]
        if limpos == valores:
            continue
        campo["value"] = limpos
        attrs["dieta"] = campo
        meta["attributes"] = attrs
        produto.metadata = meta
        produto.save(update_fields=["metadata"])


def devolve_opcoes(apps, schema_editor):
    """Reverte o vocabulário. NÃO reescreve as afirmações apagadas — de propósito."""
    AttributeDefinition = apps.get_model("shop", "AttributeDefinition")
    dd = AttributeDefinition.objects.filter(ref="dieta").first()
    if dd is not None:
        dd.options = _opcoes(DIETA_ANTIGA)
        dd.save(update_fields=["options"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0034_attribute_extends_from_source")]

    operations = [migrations.RunPython(completa_e_limpa, devolve_opcoes)]
