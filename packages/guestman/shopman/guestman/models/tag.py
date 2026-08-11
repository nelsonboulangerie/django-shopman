"""CustomerTag — as etiquetas que o operador cria para juntar pessoas.

Muitas por cliente, livres, criadas por quem atende, e **não mexem em preço** — é o que as
separa da `PriceTier` (uma por cliente, e ela precifica).

⚠️ Modelo de tag PRÓPRIO, não o `taggit.Tag` padrão. O projeto já usa taggit em
`Product.keywords` (palavras-chave de SEO), e o `Tag` padrão é um namespace GLOBAL: com ele,
"integral" e "sem lactose" do catálogo apareceriam no seletor de etiquetas de cliente, e uma
etiqueta de cliente poluiria a busca da loja. Duas perguntas diferentes com um dono só de
vocabulário — exatamente o erro que este projeto persegue.

Por que uma entidade aqui se a regra é evitar criar entidade: a etiqueta atende dois dos
quatro critérios de propriedade — **query indexada** (a audiência filtra por ela) e
**cardinalidade > 1** (várias por cliente). Uma lista em JSON no `Customer.metadata` não dá
índice nem integridade de nome, e renomear "corredores" viraria varredura de linha a linha.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from taggit.models import GenericTaggedItemBase, TagBase


class CustomerTag(TagBase):
    """Uma etiqueta de cliente. O `name` é o que o operador escreve; o `slug`, taggit faz."""

    class Meta:
        verbose_name = _("etiqueta")
        verbose_name_plural = _("etiquetas")
        ordering = ["name"]


class TaggedCustomer(GenericTaggedItemBase):
    """A ligação cliente ↔ etiqueta. Existe para dar namespace próprio ao `CustomerTag`."""

    tag = models.ForeignKey(
        CustomerTag,
        on_delete=models.CASCADE,
        related_name="tagged_items",
        verbose_name=_("etiqueta"),
    )

    class Meta:
        verbose_name = _("cliente etiquetado")
        verbose_name_plural = _("clientes etiquetados")
