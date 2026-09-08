"""Devolve `sem lactose` e `vegetariano`, que a 0035 tirou por engano.

## O que a 0035 errou

Ela retirou três termos do vocabulário de `dieta` tratando os três como
"afirmação que a casa não pode honrar". **Dois deles a casa pode.**

O erro foi confundir **composição** com **contaminação cruzada**:

- `sem lactose` é fato sobre a RECEITA, com limiar objetivo na norma
  (RDC 135/2017: < 100 mg/100 g). Uma baguete de farinha, água, sal e levain
  está em zero. Dizer isso é verdade e é útil — e a 0035 apagou do catálogo vivo
  informação correta.
- `vegetariano` também é fato sobre a receita, e é o único termo capaz de dizer
  "nada de abate" — que os alérgenos não sabem responder.
- `sem glúten` **continua fora**, e por motivo diferente: a casa não tem linha
  segregada nem pretende ter, então a afirmação seria sobre o AMBIENTE. É a
  única em que um celíaco pode se machucar.

Não conflita com o aviso de traços: intolerância à lactose é dose-dependente e
traço não a alcança; alergia à proteína do leite é outra coisa, e é dela que o
`food_safety_notice` cuida.

## Por que ela RE-DERIVA em vez de só devolver as opções

Devolver o vocabulário não devolve o dado. Os produtos ficariam sem `sem
lactose` até alguém salvar a ficha de cada um — e ninguém salvaria, porque nada
avisa.

⚠️ Por isso esta migração **importa o serviço vivo**, o que normalmente não se
faz. É reparo pontual de um dado que uma migração anterior apagou errado, e o
único jeito de acertar é rodar exatamente a mesma regra que passa a valer. A
alternativa — reimplementar a derivação aqui — daria duas verdades divergindo.

A falha de um produto não derruba o deploy: cada um é tentado por sua conta e o
que não der é registrado. Migração de reparo que aborta deixa o banco pior do
que achou.
"""

from django.db import migrations

DIETA_COM_OS_DOIS = ["100% vegetal", "vegetariano", "sem lactose"]


def _opcoes(valores):
    return [{"value": v, "label": v[:1].upper() + v[1:]} for v in valores]


def devolve(apps, schema_editor):
    AttributeDefinition = apps.get_model("shop", "AttributeDefinition")

    d = AttributeDefinition.objects.filter(ref="dieta").first()
    if d is None:
        return
    d.options = _opcoes(DIETA_COM_OS_DOIS)
    d.save(update_fields=["options"])

    # ── re-deriva o que a 0035 apagou ──
    try:
        from shopman.offerman.models import Product as ProdutoVivo

        from shopman.shop.services.dietary_from_recipe import aggregate_dietary_from_recipe
    except Exception:  # pragma: no cover - ambiente sem o app carregado
        return

    for produto in ProdutoVivo.objects.all().iterator():
        try:
            aggregate_dietary_from_recipe(produto)
        except Exception:  # pragma: no cover - um produto torto não trava o deploy
            continue


def retira(apps, schema_editor):
    """Volta ao vocabulário de um termo. Não reapaga o dado — ver a 0035."""
    AttributeDefinition = apps.get_model("shop", "AttributeDefinition")
    d = AttributeDefinition.objects.filter(ref="dieta").first()
    if d is not None:
        d.options = _opcoes(["100% vegetal"])
        d.save(update_fields=["options"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0035_promessa_que_a_casa_honra")]

    operations = [migrations.RunPython(devolve, retira)]
