from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class MaterialConversion(models.Model):
    """Quanto vale, na unidade-base do insumo, um vocabulário humano.

    A padaria fala três línguas ao mesmo tempo: o que ela **compra** (saco,
    caixa, fardo, cartela), o que ela **conta fácil** (ovo, limão, pacote) e o
    que ela **mede na verdade** (kg, l, un). A terceira é a unidade-base do
    ``Material`` e é a única em que estoque e dinheiro existem (ADR-024, R1).
    Esta tabela é a ponte para as outras duas — **declarada**, com autor e data,
    nunca deduzida (R2 e R4).

    O que **não** mora aqui: kg↔g, l↔ml, dz↔un. Isso é física, é fechado em
    código (:mod:`shopman.utils.units`) e ninguém edita — se morasse no banco,
    alguém salvaria "1 kg = 900 g" e o sistema obedeceria calado.

    Dois tipos, e a diferença entre eles é justamente o que não pode sumir:

    - ``conventional`` — exata **por convenção declarada**: "saco = 25 kg" é
      verdade porque o moinho embalou assim. Muda quando o fornecedor muda, e é
      por isso que é editável em vez de constante;
    - ``approximate`` — equivalência **física**, que carrega incerteza: "1 ovo
      ≈ 50 g". Número que passou por aqui é rotulado até a tela (R3): some o
      ``≈``, some a informação.

    ``supplier`` nulo significa "vale para qualquer fornecedor" — é o caso comum
    da equivalência aproximada, que é do insumo, não de quem vende. Quando o
    mesmo insumo chega em embalagens diferentes por fornecedor, a linha ganha
    dono.

    ``created_by`` existe porque a ADR-024 diz que estas duas espécies "têm
    autor", e porque o recebimento passou a ser um lugar onde elas nascem: um
    fator errado muda estoque e dinheiro de toda compra seguinte, então tem de
    dar para perguntar quem declarou.
    """

    class Kind(models.TextChoices):
        CONVENTIONAL = "conventional", _("convencionada")
        APPROXIMATE = "approximate", _("aproximada")

    material = models.ForeignKey(
        "buyman.Material", on_delete=models.CASCADE, related_name="conversions",
        verbose_name=_("Insumo"),
    )
    supplier = models.ForeignKey(
        "buyman.Supplier", on_delete=models.CASCADE, related_name="material_conversions",
        null=True, blank=True, verbose_name=_("Fornecedor"),
        help_text=_("Vazio = vale para qualquer fornecedor."),
    )
    label = models.CharField(
        max_length=60, verbose_name=_("Rótulo"),
        help_text=_(
            "Como o operador chama isto: 'saco 25 kg', 'cartela', 'ovos'. "
            "É o texto que aparece na tela, tal como escrito aqui."
        ),
    )
    to_base_factor = models.DecimalField(
        max_digits=16, decimal_places=6, verbose_name=_("Fator para a unidade-base"),
        help_text=_(
            "Quanto UM desta embalagem/contagem vale na unidade-base do insumo. "
            "Saco de 25 kg com base kg: 25. Ovo com base kg: 0,05."
        ),
    )
    kind = models.CharField(
        max_length=16, choices=Kind.choices, default=Kind.CONVENTIONAL,
        verbose_name=_("Tipo"),
        help_text=_(
            "Convencionada = exata por declaração do fornecedor. "
            "Aproximada = equivalência física, e o número carrega '≈' até a tela."
        ),
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Ativa"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name=_("Declarada por"),
        help_text=_("Quem declarou o fator. Vazio nas linhas anteriores ao registro de autoria."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Criada em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Atualizada em"))

    class Meta:
        verbose_name = _("conversão de insumo")
        verbose_name_plural = _("conversões de insumo")
        ordering = ["material", "label"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(to_base_factor__gt=0),
                name="buyman_conversion_factor_positive",
                violation_error_message=_(
                    "O fator precisa ser maior que zero — fator zero ou negativo "
                    "transformaria a conversão num número sem sentido."
                ),
            ),
            # Duas constraints porque NULL não colide com NULL no banco: sem a
            # segunda, "cartela" sem fornecedor poderia ser cadastrada duas vezes
            # no mesmo insumo e ninguém saberia qual fator valeu.
            models.UniqueConstraint(
                fields=["material", "supplier", "label"],
                condition=models.Q(supplier__isnull=False),
                name="buyman_conversion_label_unique_per_supplier",
                violation_error_message=_(
                    "Este insumo já tem uma conversão com este rótulo para este "
                    "fornecedor. Edite a existente em vez de criar uma segunda."
                ),
            ),
            models.UniqueConstraint(
                fields=["material", "label"],
                condition=models.Q(supplier__isnull=True),
                name="buyman_conversion_label_unique_any_supplier",
                violation_error_message=_(
                    "Este insumo já tem uma conversão com este rótulo valendo para "
                    "qualquer fornecedor. Edite a existente ou dê um rótulo próprio."
                ),
            ),
        ]

    @property
    def is_approximate(self) -> bool:
        """``True`` quando o número que sai daqui precisa do ``≈`` na tela."""
        return self.kind == self.Kind.APPROXIMATE

    def clean(self):
        super().clean()
        self.label = (self.label or "").strip()
        if not self.label:
            raise ValidationError({"label": _("O rótulo é obrigatório.")})
        if self.to_base_factor is not None and self.to_base_factor <= 0:
            raise ValidationError({
                "to_base_factor": _("O fator precisa ser maior que zero.")
            })

    def __str__(self) -> str:
        unit = getattr(self.material, "unit", "") if self.material_id else ""
        prefix = "≈ " if self.is_approximate else ""
        return f"{self.label} = {prefix}{self.to_base_factor} {unit}".strip()
