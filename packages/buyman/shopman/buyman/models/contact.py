from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from shopman.utils.phone import normalize_phone


class SupplierContact(models.Model):
    """A pessoa do fornecedor — quem atende, e sobre qual assunto.

    O :class:`~shopman.buyman.models.supplier.Supplier` guarda a **empresa**:
    razão social, CNPJ, e o e-mail/telefone da central. Isso basta para o
    sistema conseguir falar com o fornecedor, e não basta para falar com
    alguém. Um pedido de compra que abre com a razão social ("Olá, INDUSTRIA E
    COMERCIO DE PRODUTOS ALIMENTICIOS TAMURA LTDA.") está tecnicamente correto e
    socialmente errado — do outro lado tem uma pessoa que tem nome.

    **O papel existe porque o roteamento existe, não como taxonomia.** Já saem
    daqui dois documentos diferentes para o mesmo fornecedor — o pedido de
    compra e a recusa de recebimento — e na vida real eles não caem na mesma
    caixa de entrada: pedido é assunto do comercial, devolução por lote/validade
    é assunto de quem responde por qualidade, e divergência de valor é do
    financeiro. Sem papel, os três chegam ao vendedor, que reencaminha à mão e
    perde um dia. Se um dia um papel deixar de mudar para onde a mensagem vai,
    ele deixa de ter razão para existir aqui.

    Logística não é papel: transportadora terceirizada é *outro* fornecedor —
    de serviço — com contato próprio, e não uma pessoa dentro deste.

    Duas invariantes, cada uma com o guarda à altura:

    - **contato sem meio de contato não é contato** — ``CheckConstraint`` exige
      e-mail ou telefone; um nome solto na tabela é uma rota que falha só na
      hora de enviar, que é a pior hora de descobrir;
    - **um principal por papel** — ``UniqueConstraint`` parcial, e promover um
      novo demove o anterior na mesma transação, para o operador nunca ver
      ``IntegrityError`` cru na tela do inline (mesmo gesto de
      :class:`~shopman.buyman.models.cost.SupplierMaterialCost`).
    """

    class Role(models.TextChoices):
        SALES = "sales", _("Comercial")
        FINANCE = "finance", _("Financeiro")
        QUALITY = "quality", _("Qualidade")
        GENERAL = "general", _("Geral")

    supplier = models.ForeignKey(
        "buyman.Supplier",
        on_delete=models.CASCADE,
        related_name="contacts",
        verbose_name=_("Fornecedor"),
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_("Nome"),
        help_text=_("Como a pessoa se apresenta — é assim que a mensagem vai cumprimentá-la."),
    )
    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.GENERAL,
        db_index=True,
        verbose_name=_("Papel"),
        help_text=_(
            "Decide qual documento chega a esta pessoa: o pedido de compra vai "
            "para o comercial, a recusa de recebimento para a qualidade. "
            "'Geral' recebe o que não tiver dono."
        ),
    )
    email = models.EmailField(blank=True, default="", verbose_name=_("E-mail"))
    phone = models.CharField(
        max_length=32, blank=True, default="", verbose_name=_("Telefone/WhatsApp"),
    )
    is_primary = models.BooleanField(
        default=False,
        verbose_name=_("Principal"),
        help_text=_("O contato preferido deste papel. Um por papel."),
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Ativo"))
    notes = models.TextField(
        blank=True, default="", verbose_name=_("Observações"),
        help_text=_("Horário em que atende, quem substitui nas férias, o que for útil."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Atualizado em"))

    class Meta:
        verbose_name = _("contato do fornecedor")
        verbose_name_plural = _("contatos do fornecedor")
        ordering = ["supplier", "role", "-is_primary", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "role"],
                condition=models.Q(is_primary=True),
                name="buyman_one_primary_contact_per_role",
            ),
            models.CheckConstraint(
                condition=~(models.Q(email="") & models.Q(phone="")),
                name="buyman_contact_needs_a_way_to_reach",
                violation_error_message=_("Informe e-mail ou telefone para este contato."),
            ),
        ]
        indexes = [
            models.Index(fields=["supplier", "role", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_role_display()})"

    @property
    def first_name(self) -> str:
        """O primeiro nome — é com ele que se cumprimenta, não com o nome inteiro."""
        return (self.name or "").strip().split(" ")[0]

    @classmethod
    def pick(cls, contacts, role: str, *, requires: str = "") -> "SupplierContact | None":
        """Quem responde por este assunto, escolhido de uma lista já carregada.

        Procura o papel pedido e, se ninguém atender, o geral — nessa ordem, e
        nunca o contrário: cair no vendedor por falta de alguém da qualidade é
        um incômodo, cair na qualidade por falta do vendedor é um pedido de
        compra perdido.

        ``requires`` ("email" ou "phone") descarta quem não tem o meio pelo qual
        a mensagem vai sair. O comprador que só deixou telefone não pode vencer
        a rota de e-mail e sumir com o pedido — para o sistema, ele não é
        alcançável por ali.

        A regra mora aqui, e não no ``resolve``, para a tela poder aplicá-la
        sobre um ``prefetch_related`` sem uma consulta por fornecedor **e** sem
        uma segunda cópia da ordem de preferência para sair de sincronia.
        """
        usable = [
            contact
            for contact in contacts
            if contact.is_active and (not requires or getattr(contact, requires, ""))
        ]
        for wanted in (role, cls.Role.GENERAL):
            found = sorted(
                (c for c in usable if c.role == wanted),
                key=lambda c: (not c.is_primary, c.name or ""),
            )
            if found:
                return found[0]
        return None

    @classmethod
    def resolve(cls, supplier, role: str, *, requires: str = "") -> "SupplierContact | None":
        """``pick`` indo ao banco: para quem tem um fornecedor e nenhuma lista."""
        if supplier is None:
            return None
        return cls.pick(cls.objects.filter(supplier=supplier), role, requires=requires)

    def clean(self):
        super().clean()
        self._refuse_contact_without_reach()
        self._refuse_retired_primary()

    def save(self, *args, **kwargs):
        """Normaliza o telefone, adota o primeiro do papel e promove sem colisão."""
        self.phone = normalize_phone(self.phone) if self.phone else ""
        self.email = (self.email or "").strip().lower()
        self._refuse_contact_without_reach()
        self._refuse_retired_primary()

        with transaction.atomic():
            # O primeiro de um papel é o principal por definição: exigir a
            # caixinha marcada só produziria fornecedor com um contato e
            # nenhum principal — e rota que não resolve.
            if not self.pk and self.supplier_id and self.is_active:
                taken = (
                    type(self)
                    .objects.filter(supplier_id=self.supplier_id, role=self.role, is_primary=True)
                    .exists()
                )
                if not taken:
                    self.is_primary = True
            if self.is_primary and self.supplier_id:
                (
                    type(self)
                    .objects.filter(
                        supplier_id=self.supplier_id, role=self.role, is_primary=True,
                    )
                    .exclude(pk=self.pk)
                    .update(is_primary=False)
                )
            super().save(*args, **kwargs)

    def _refuse_contact_without_reach(self) -> None:
        if not (self.email or self.phone):
            raise ValidationError({
                "email": _(
                    "Um contato precisa de e-mail ou telefone — sem isso ele é um "
                    "nome que o sistema não consegue avisar."
                )
            })

    def _refuse_retired_primary(self) -> None:
        """Principal inativo é rota apontando para quem não atende mais."""
        if self.is_primary and not self.is_active:
            raise ValidationError({
                "is_primary": _(
                    "Um contato inativo não pode ser o principal. Promova outra "
                    "pessoa deste papel antes de aposentar esta."
                )
            })
