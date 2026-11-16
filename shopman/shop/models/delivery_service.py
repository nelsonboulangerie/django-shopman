"""Quem leva a entrega: os serviços de entrega, os entregadores da casa e os valores deles.

Plano: ``docs/plans/DELIVERY-MULTI-SERVICE-PLAN.md`` (DEV-2026-030, decidido pelo dono em
16/11/2026). Esta é a frente M0, só o cadastro: nada aqui é lido pelo despacho ainda. O
contrato de serviço (``DeliveryServiceBackend``) nasce na M1, com a TaOn conformada, e o
entregador da casa vira a segunda implementação na M2.

Configuração de loja mora no banco, nunca em env nem em ``settings`` (ADR-042).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class DeliveryService(models.Model):
    """Um serviço que leva entregas da casa: a central da TaOn, os entregadores da casa, outra API.

    O nome é o que o OPERADOR vê no Gestor ("TaOn", "Entregadores da casa"); ao cliente o
    serviço nunca aparece. ``kind`` é lista fechada no código: cada valor é uma
    implementação, não um caminho livre de módulo.

    O padrão (``is_default``) é o que vem marcado no "Chamar entregador" e o que o despacho
    automático usa (decisão do dono, 16/11/2026: configurável no Admin, hoje a TaOn). Um só
    por loja.
    """

    KIND_MACHINE = "machine"
    KIND_OWN_FLEET = "own_fleet"
    KIND_CHOICES = [
        (KIND_MACHINE, "Central de entregas por API (TaOn)"),
        (KIND_OWN_FLEET, "Entregadores da casa"),
    ]

    ref = models.SlugField(
        "identificador",
        max_length=40,
        unique=True,
        help_text="Nome estável usado pelo sistema (ex.: taon, casa). Não muda depois de criado.",
    )
    name = models.CharField(
        "nome",
        max_length=60,
        help_text="Como o operador vê este serviço no Gestor. O cliente nunca vê.",
    )
    kind = models.CharField("tipo", max_length=20, choices=KIND_CHOICES)
    is_default = models.BooleanField(
        "padrão",
        default=False,
        help_text="Vem marcado ao chamar o entregador e é o que o despacho automático usa. Um só.",
    )
    is_active = models.BooleanField("ativo", default=True)
    sort_order = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "serviço de entrega"
        verbose_name_plural = "serviços de entrega"
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True),
                name="shop_deliveryservice_one_default",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.is_default and not self.is_active:
            raise ValidationError({"is_default": "O serviço padrão precisa estar ativo."})
        if self.is_default:
            other = DeliveryService.objects.filter(is_default=True).exclude(pk=self.pk).first()
            if other is not None:
                raise ValidationError(
                    {"is_default": f"O padrão hoje é {other.name}. Desmarque lá antes de marcar aqui."}
                )

    @property
    def is_own_fleet(self) -> bool:
        return self.kind == self.KIND_OWN_FLEET

    @classmethod
    def default(cls) -> DeliveryService | None:
        """O serviço padrão ativo, ou None quando não há um."""
        return cls.objects.filter(is_default=True, is_active=True).first()


def _require_own_fleet(service: DeliveryService | None, field: str) -> None:
    if service is not None and not service.is_own_fleet:
        raise ValidationError({field: "Só serviço do tipo Entregadores da casa tem entregador e tabela de valores."})


class Courier(models.Model):
    """Um entregador da casa.

    O mínimo para a casa chamar e ele receber: nome, WhatsApp (por onde vai o link da
    corrida) e o veículo, que a Saída mostra para conferir antes de entregar as sacolas.
    Sem CPF e sem chave Pix: o pagamento do entregador é por fora (decisão do dono, 16/11).
    """

    service = models.ForeignKey(
        DeliveryService,
        on_delete=models.PROTECT,
        related_name="couriers",
        verbose_name="serviço",
        limit_choices_to={"kind": DeliveryService.KIND_OWN_FLEET},
    )
    ref = models.SlugField("identificador", max_length=40, unique=True)
    name = models.CharField("nome", max_length=60, help_text="Como a casa chama o entregador (ex.: Diego).")
    phone = models.CharField(
        "WhatsApp",
        max_length=20,
        help_text="Por onde o entregador recebe o link da corrida. Com DDD.",
    )
    vehicle = models.CharField(
        "veículo",
        max_length=60,
        blank=True,
        help_text="O que o balcão confere antes de entregar as sacolas (ex.: Moto prata · ABC1D23).",
    )
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "entregador da casa"
        verbose_name_plural = "entregadores da casa"

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.service_id:
            _require_own_fleet(self.service, "service")
        if self.phone:
            from shopman.utils.phone import is_valid_phone, normalize_phone

            normalized = normalize_phone(self.phone)
            if not normalized or not is_valid_phone(normalized):
                raise ValidationError({"phone": "Telefone inválido. Escreva com DDD, ex.: (43) 99999-0000."})
            self.phone = normalized


class CourierRate(models.Model):
    """Uma linha da tabela de valores dos entregadores da casa.

    A tabela da casa são as linhas sem entregador: "até 3 km R$ 8,00", "até 6 km R$ 12,00".
    A linha sem distância máxima vale para qualquer distância (o valor fixo). Quando um
    entregador tem linhas próprias, elas substituem a tabela da casa para ele (o valor
    combinado com ele). A régua que escolhe a linha e soma os extras é
    ``shopman.shop.services.delivery_rates.ride_value``.
    """

    service = models.ForeignKey(
        DeliveryService,
        on_delete=models.CASCADE,
        related_name="rates",
        verbose_name="serviço",
        limit_choices_to={"kind": DeliveryService.KIND_OWN_FLEET},
    )
    courier = models.ForeignKey(
        Courier,
        on_delete=models.CASCADE,
        related_name="rates",
        verbose_name="entregador",
        null=True,
        blank=True,
        help_text="Vazio: vale para todos (tabela da casa). Preenchido: o valor combinado com este entregador.",
    )
    max_km = models.DecimalField(
        "até (km)",
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Distância da rota inteira, com a volta quando houver. Vazio: qualquer distância.",
    )
    value_q = models.PositiveIntegerField("valor da corrida (centavos)", help_text="Ex.: 1200 = R$ 12,00.")
    extra_stop_q = models.PositiveIntegerField(
        "por parada a mais (centavos)",
        default=0,
        help_text="Somado por pedido além do primeiro na mesma corrida.",
    )
    return_q = models.PositiveIntegerField(
        "com volta à loja (centavos)",
        default=0,
        help_text="Somado quando a corrida volta à loja (cobrança na porta ou maquininha).",
    )

    class Meta:
        ordering = ["service", "courier", "max_km"]
        verbose_name = "valor de entregador"
        verbose_name_plural = "valores dos entregadores"

    def __str__(self) -> str:
        who = self.courier.name if self.courier_id else "Tabela da casa"
        reach = f"até {self.max_km} km" if self.max_km is not None else "qualquer distância"
        return f"{who} · {reach} · R$ {self.value_q / 100:.2f}".replace(".", ",")

    def clean(self) -> None:
        super().clean()
        if self.service_id:
            _require_own_fleet(self.service, "service")
        if self.courier_id and self.service_id and self.courier.service_id != self.service_id:
            raise ValidationError({"courier": "Este entregador é de outro serviço."})
        if self.max_km is not None and self.max_km <= 0:
            raise ValidationError({"max_km": "A distância precisa ser maior que zero."})
        if self.service_id:
            twin = CourierRate.objects.filter(
                service_id=self.service_id,
                courier_id=self.courier_id,
                max_km=self.max_km,
            ).exclude(pk=self.pk)
            if twin.exists():
                raise ValidationError({"max_km": "Já existe uma linha com esta distância para o mesmo entregador."})
