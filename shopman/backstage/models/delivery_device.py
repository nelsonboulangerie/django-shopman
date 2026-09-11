"""Physical delivery card readers; current custody is exclusive across orders."""
import uuid

from django.db import models


class DeliveryDevice(models.Model):
    ref = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    label = models.CharField("nome/apelido", max_length=100)
    identification = models.CharField("identificação", max_length=100, unique=True)
    active = models.BooleanField("ativa", default=True)
    current_order = models.OneToOneField(
        "orderman.Order", null=True, blank=True, editable=False,
        on_delete=models.PROTECT, related_name="delivery_device",
        verbose_name="entrega atual",
    )

    class Meta:
        ordering = ("label", "pk")
        verbose_name = "maquininha de entrega"
        verbose_name_plural = "maquininhas de entrega"

    def __str__(self):
        return self.label
