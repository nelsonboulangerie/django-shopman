"""Trilha do apply do descritor de Instância: quem aplicou, quando, o quê.

Cada ``instance_descriptor apply`` que muda o banco grava uma linha. O
``descriptor`` guardado é o DECLARADO (não o resultado): é a base da comparação
de três vias do próximo apply. Valor que está no banco diferente da última
versão declarada foi mudado por fora (pelo operador, no Admin) e o apply não o
sobrescreve sem ordem explícita (``config/instance_descriptors.py``).

A linha é imutável por contrato: o apply só insere.
"""

from django.db import models


class InstanceApplyRecord(models.Model):
    instance_ref = models.CharField("instância", max_length=80, db_index=True)
    schema_version = models.PositiveIntegerField("versão do esquema")
    descriptor_sha256 = models.CharField("hash do descritor", max_length=64)
    descriptor = models.JSONField(
        "descritor declarado",
        help_text="O descritor como foi declarado; base do próximo apply.",
    )
    changes = models.JSONField("mudanças", default=list)
    actor = models.CharField("quem aplicou", max_length=160)
    on_drift = models.CharField("política de divergência", max_length=16)
    applied_at = models.DateTimeField("aplicado em", auto_now_add=True)

    class Meta:
        verbose_name = "aplicação do descritor de Instância"
        verbose_name_plural = "aplicações do descritor de Instância"
        ordering = ["-applied_at", "-pk"]

    def __str__(self) -> str:
        return f"{self.instance_ref} {self.descriptor_sha256[:12]} por {self.actor}"
