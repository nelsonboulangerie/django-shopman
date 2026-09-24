"""A lápide de um produto apagado: o que a loja responde quando o endereço fica órfão.

Produto apagado não deixa rastro no banco — e a loja passa a responder 404 mudo
para um endereço que o Google indexou, que alguém salvou nos favoritos e que
ainda circula em link de rede social. 404 diz "nunca vi isso aqui"; a verdade é
outra: existia, saiu, e não volta.

Decisão do dono em 23/09/2026: a loja diz **não existe mais** (410) e oferece a
coleção de onde o produto saiu, para a pessoa não terminar num beco.

Duas escolhas do formato, e as duas vêm do catálogo real:

- **Coleções, no plural.** Produto mora em mais de uma vitrine, e guardar uma só
  obrigaria a escolher — errando, manda o cliente para a prateleira errada.
- **Pode não ter nenhuma.** O ``COMBO-PETIT-DEJ`` era o único item de "Combos", e
  a coleção ficou vazia quando ele saiu. Mandar alguém para uma prateleira vazia
  é pior que não mandar.
"""

from django.db import models


class RetiredProduct(models.Model):
    """Um SKU que existiu no catálogo e foi apagado."""

    sku = models.CharField("SKU", max_length=64, unique=True)
    collection_refs = models.TextField(
        "coleções",
        blank=True,
        help_text="Refs separadas por vírgula, na ordem em que a loja deve oferecer. "
                  "Vazio = a tela só oferece o cardápio.",
    )
    note = models.CharField(
        "observação",
        max_length=200,
        blank=True,
        help_text="Por que saiu, para quem ler isto daqui a um ano.",
    )
    created_at = models.DateTimeField("registrado em", auto_now_add=True)

    class Meta:
        verbose_name = "produto aposentado"
        verbose_name_plural = "produtos aposentados"
        ordering = ["sku"]

    def __str__(self) -> str:
        return self.sku

    @property
    def refs(self) -> list[str]:
        """As refs de coleção, sem espaço nem vazio, na ordem gravada."""
        return [ref.strip() for ref in (self.collection_refs or "").split(",") if ref.strip()]
