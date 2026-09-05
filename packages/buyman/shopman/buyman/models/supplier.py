from django.db import models
from django.utils.translation import gettext_lazy as _
from shopman.refs.fields import RefField


class Supplier(models.Model):
    """Fornecedor (lado montante) — a **empresa**.

    A pessoa com quem se fala mora em
    :class:`~shopman.buyman.models.contact.SupplierContact`; ``email`` e
    ``phone`` aqui são a **central** da empresa, o canal que atende quando
    ninguém em particular foi cadastrado. Manter os dois separados é o que
    permite a rota cair da pessoa para a casa sem inventar um contato que não
    existe.
    """

    ref = RefField(
        ref_type="SUPPLIER",
        unique=True,
        verbose_name=_("Referência"),
        help_text=_("Identificador do fornecedor (ex.: moinho-sp)."),
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_("Razão social"),
        help_text=_("O nome do contrato e da nota fiscal."),
    )
    trade_name = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name=_("Nome fantasia"),
        help_text=_(
            "Como a casa chama este fornecedor no dia a dia ('Tamura'). É este "
            "nome que aparece nas mensagens — ninguém cumprimenta uma razão social."
        ),
    )
    document = models.CharField(
        max_length=32, blank=True, default="", verbose_name=_("CNPJ/Documento"),
    )
    email = models.EmailField(
        blank=True, default="", verbose_name=_("E-mail da central"),
        help_text=_("Caixa geral da empresa. Só é usada quando nenhum contato atende o assunto."),
    )
    phone = models.CharField(
        max_length=32, blank=True, default="", verbose_name=_("Telefone da central"),
        help_text=_("Telefone geral da empresa, usado como último recurso."),
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Ativo"))
    metadata = models.JSONField(default=dict, blank=True, verbose_name=_("Metadados"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Atualizado em"))

    class Meta:
        verbose_name = _("fornecedor")
        verbose_name_plural = _("fornecedores")
        ordering = ["name"]

    @property
    def display_name(self) -> str:
        """O nome com que se fala deste fornecedor: fantasia, senão razão social."""
        return (self.trade_name or "").strip() or (self.name or "").strip() or self.ref

    def __str__(self) -> str:
        return self.display_name
