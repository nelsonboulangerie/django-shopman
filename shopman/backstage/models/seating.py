"""Os lugares do salão — o denominador que faltava para medir ociosidade.

Sem saber quantos lugares a casa tem, "3 grupos sentados" não vira "sobra mesa"
nem "está cheio". É a única coisa que este bloco captura, e ela se cadastra uma
vez: ninguém no balcão passa por aqui.

**Não há vínculo comanda↔mesa, de propósito.** No ato de abrir a comanda a
pessoa ainda não sabe onde vai sentar, e forçar a escolha produziria mesa errada
ou mesa em branco — métrica mentirosa é pior que métrica ausente. Das seis
perguntas de salão, só "qual mesa rende mais" precisaria do vínculo, e é a menos
acionável. As outras cinco saem da lotação, que se mede sem ele.

⚠️ **A capacidade oficial da Nelson não é um limite duro** (informado pelo dono):
as mesas internas têm um sofá que permite apertar, há duas mesinhas altas de
bistrô e um bancão externo que, em dia cheio, comportam mais gente. Esses ficam
FORA da conta — ``counts_in_capacity=False`` — porque o que interessa medir é
**quantas vezes a casa bateu no teto oficial**, que é justamente o momento em que
o espaço elástico entra em uso. Denominador elástico não admite numerador
preciso: é por isso que a leitura sai em faixas, e não em porcentagem com
decimal.
"""

from __future__ import annotations

from django.db import models


class SpotKind(models.TextChoices):
    TABLE = "table", "Mesa"
    COUNTER = "counter", "Lugar de balcão"


class SeatingSpot(models.Model):
    """Um lugar onde um grupo pode sentar.

    ``active_from``/``active_until`` existem para que o passado não seja
    reescrito: mesa acrescentada em março não pode fazer janeiro parecer mais
    vazio do que foi.
    """

    ref = models.SlugField("ref", max_length=32, unique=True)
    label = models.CharField("rótulo", max_length=80)
    kind = models.CharField("tipo", max_length=16, choices=SpotKind.choices, default=SpotKind.TABLE)
    area = models.CharField(
        "área", max_length=40, blank=True,
        help_text="Salão interno, calçada, balcão. Só para o gestor se localizar.",
    )
    seats = models.PositiveSmallIntegerField(
        "lugares", default=2,
        help_text="Quantas pessoas cabem com conforto. A casa aperta mais; isto é o nominal.",
    )
    counts_in_capacity = models.BooleanField(
        "conta na capacidade oficial", default=True,
        help_text=(
            "Desmarque o que só é usado em dia cheio (bistrô em pé, bancão "
            "externo). Fora da conta, eles não escondem o momento em que a "
            "casa bateu no teto — que é o que interessa medir."
        ),
    )
    active_from = models.DateField(
        "existe desde", null=True, blank=True,
        help_text="Vazio = sempre existiu. Preencher evita reescrever o passado.",
    )
    active_until = models.DateField("existiu até", null=True, blank=True)

    class Meta:
        verbose_name = "lugar do salão"
        verbose_name_plural = "lugares do salão"
        ordering = ["kind", "ref"]

    def __str__(self) -> str:
        return self.label

    def existed_on(self, day) -> bool:
        if self.active_from and day < self.active_from:
            return False
        return not (self.active_until and day > self.active_until)
