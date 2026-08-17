"""Etiquetas de produto que sustentam a inferência de modo de consumo.

O sistema não registra quem sentou e quem levou — e a decisão do dono (17/08) é
**não passar a registrar**: o modo de consumo se lê da cesta. Isso vale para
trás (os dois anos do histórico externo) e não depende de ninguém lembrar de
apertar nada.

Para a cesta falar, cada produto precisa de um **papel**. É a mesma forma dos
defeitos de qualidade e dos tipos de episódio: catálogo editável no Admin, com o
comportamento declarado em campo — não em código. Assim, cadastrar "sorvete na
casquinha" como algo que ancora consumo local não pede deploy.

⚠️ **A etiqueta é curadoria humana, produto a produto.** O nome não classifica:
"Hambúrguer 100g" na Nelson é o **pão** de hambúrguer, não o sanduíche montado —
e etiquetá-lo pelo nome leria toda compra de pão de churrasco como alguém
almoçando na casa. Quem revisa precisa conhecer o cardápio.

Produto sem etiqueta **não vira "levar" por omissão**: a venda inteira sai como
não classificada, e a tela declara a cobertura. Ausência de dado é ausência de
dado.
"""

from __future__ import annotations

from django.db import models


class Reading(models.TextChoices):
    """O que a presença do produto na cesta diz. São exatamente três coisas.

    Não é acaso serem três: são as três que a regra sabe usar. Um vocabulário
    maior (bebida preparada, bebida pronta, prato quente, lanche montado…) seria
    quatro nomes para a MESMA leitura — mais escolhas do que consequências, e um
    convite a achar que a distinção muda alguma coisa. Ela não muda.
    """

    ANCHOR = "anchor", "Consome aqui"
    TAKEAWAY = "takeaway", "Leva"
    NEUTRAL = "neutral", "Acompanha"


class ConsumptionRole(models.Model):
    """Papel de um produto na cesta — o vocabulário da inferência.

    O catálogo continua editável (a casa nomeia como quiser: "café", "salgado
    assado", "geleia"), mas cada nome escolhe UMA das três leituras. É a
    diferença entre dar nome ao que a casa vende e inventar comportamento novo
    — comportamento muda com teste, não com cadastro.
    """

    ref = models.SlugField("ref", max_length=32, unique=True)
    label = models.CharField("rótulo", max_length=80)
    hint = models.CharField(
        "dica", max_length=140, blank=True,
        help_text="Para quem etiqueta escolher sem pensar duas vezes.",
    )
    reading = models.CharField(
        "o que diz sobre a cesta", max_length=16,
        choices=Reading.choices, default=Reading.NEUTRAL,
        help_text=(
            "Consome aqui: bebida, prato, lanche — a presença indica alguém "
            "que sentou (nesta casa, levar bebida é desprezível). "
            "Leva: pão, varejo — junto de uma âncora vira 'consumiu e levou'. "
            "Acompanha: doce, viennoiserie — não decide nada sozinho, mas tira "
            "a cesta do balde 'sem etiqueta'."
        ),
    )
    is_active = models.BooleanField("ativo", default=True)
    ordering = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "papel de consumo"
        verbose_name_plural = "papéis de consumo"
        ordering = ["ordering", "label"]

    def __str__(self) -> str:
        return self.label


class ProductConsumptionTag(models.Model):
    """A VOCAÇÃO de um SKU — não um fato sobre nenhuma venda.

    Nomeado pelo dono (17/08): *"esse dado diz apenas sobre a vocação do SKU, e
    não é algo rígido"*. Croissant tem vocação ambígua; o croissant daquela
    venda pode ter sido comido ali ou levado, e ninguém sabe. É por isso que
    toda leitura derivada daqui sai rotulada como inferida, e que ela serve ao
    B.I. sem nunca mandar em decisão operacional.

    Por isso ela **não mora no modelo do produto**, e sim aqui: etiqueta de
    análise não é atributo de produto vendável, e o Offerman fica intocado.
    Chaveada por **texto do SKU**, não por FK ao catálogo — o histórico externo
    tem produtos que saíram do cardápio, e eles precisam ser classificáveis do
    mesmo jeito.
    """

    sku = models.CharField("sku", max_length=64, unique=True)
    role = models.ForeignKey(
        ConsumptionRole, on_delete=models.PROTECT,
        related_name="products", verbose_name="papel",
    )
    note = models.CharField(
        "observação", max_length=140, blank=True,
        help_text="Por que este papel, quando o nome do produto engana.",
    )
    reviewed = models.BooleanField(
        "revisada por gente", default=False,
        help_text=(
            "Etiqueta proposta pela coleção do catálogo entra FALSA. Proposta "
            "não é curadoria: o nome engana (o 'Hambúrguer 100g' é o pão), e "
            "número calculado sobre palpite não pode parecer conferido."
        ),
    )
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        verbose_name = "etiqueta de consumo"
        verbose_name_plural = "etiquetas de consumo"
        ordering = ["sku"]

    def __str__(self) -> str:
        return f"{self.sku} → {self.role_id and self.role.label}"
