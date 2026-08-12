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

    @classmethod
    def resolve(cls, names) -> list["CustomerTag"]:
        """Nomes → etiquetas, **reusando** a que já existe com o mesmo slug.

        ⚠️ Sem isto, "sem glúten" e "sem gluten" viram DUAS etiquetas. O taggit não recusa o
        segundo: o `slug` é unique, então ele resolve o conflito acrescentando sufixo
        (`sem-gluten` e `sem-gluten_1`), e ficam dois rótulos para a mesma coisa. Visto na
        tela, com uma cliente real do seed carregando os dois.

        O dano é o de sempre neste projeto — silencioso: o público por `sem-gluten` alcança
        metade das pessoas, e nada indica que a outra metade existe. Casar por slug é o que
        faz acento, maiúscula e espaço a mais convergirem para uma etiqueta só.

        Não resolve SINÔNIMO ("corredores" vs "corrida"): isso é escolha de vocabulário, e é
        por isso que a tela mostra as etiquetas que já existem antes de criar outra.
        """
        resolved: list[CustomerTag] = []
        seen: set[str] = set()
        for raw in names:
            name = str(raw).strip()
            if not name:
                continue
            slug = cls().slugify(name)
            if slug in seen:
                continue
            seen.add(slug)

            tag = cls.objects.filter(slug=slug).first()
            if tag is None:
                tag = cls.objects.create(name=name, slug=slug)
            resolved.append(tag)
        return resolved


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
