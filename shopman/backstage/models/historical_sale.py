"""Histórico externo de vendas (ADR-021 §3, BI-PLAN §7).

Fonte externa (ex.: export do Yooga) não tem ledger na suite — só pode existir
materializada, com a origem carimbada em cada linha. NÃO é second source of
truth: é o único registro que a suite tem daquele passado. Só o B.I. lê;
nada daqui entra em Order, Move, DayClosing ou relatórios operacionais.

Campos de canal: ``modality``/``origin``/``table_label`` são o dado CRU do
sistema antigo (mesa/balcão do Yooga NÃO são confiáveis — nunca virar verdade
de canal). ``is_delivery`` é o único rótulo derivado confiável: origem
DELIVERY ou forma de pagamento "Delivery -"/"IFOOD".
"""

from __future__ import annotations

from django.db import models


class HistoricalSale(models.Model):
    source = models.CharField("origem", max_length=16, default="yooga", db_index=True)
    external_id = models.BigIntegerField(
        "id externo", help_text="Chave natural no sistema de origem (ex.: pedido do Yooga)."
    )
    occurred_at = models.DateTimeField("vendido em", db_index=True)
    total_q = models.BigIntegerField("total (centavos)")
    discount_q = models.BigIntegerField("desconto (centavos)", default=0)
    surcharge_q = models.BigIntegerField("acréscimo (centavos)", default=0)
    payment = models.CharField("forma de pagamento (crua)", max_length=100, blank=True)
    operator = models.CharField("operador", max_length=100, blank=True)
    modality = models.CharField("modalidade (crua)", max_length=32, blank=True)
    origin = models.CharField("origem da venda (crua)", max_length=32, blank=True)
    table_label = models.CharField("mesa (crua)", max_length=32, blank=True)
    is_delivery = models.BooleanField(
        "é delivery", default=False,
        help_text="Único rótulo de canal confiável do histórico.",
    )
    customer_external_id = models.BigIntegerField("cliente (id externo)", null=True, blank=True)
    customer_name = models.CharField("cliente", max_length=200, blank=True)
    metadata = models.JSONField("metadata", default=dict, blank=True)
    ingested_at = models.DateTimeField("ingerido em", auto_now_add=True)

    class Meta:
        verbose_name = "venda histórica"
        verbose_name_plural = "vendas históricas"
        ordering = ["-occurred_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                name="backstage_histsale_source_external",
            ),
        ]
        indexes = [
            models.Index(fields=["source", "occurred_at"], name="backstage_hs_src_when_idx"),
        ]

    def __str__(self):
        return f"{self.source}:{self.external_id} ({self.occurred_at:%Y-%m-%d})"


class HistoricalSaleItem(models.Model):
    sale = models.ForeignKey(
        HistoricalSale, on_delete=models.CASCADE, related_name="items", verbose_name="venda"
    )
    seq = models.PositiveIntegerField("linha")
    product_name = models.CharField("produto", max_length=200)
    sku = models.CharField(
        "sku", max_length=64, blank=True, db_index=True,
        help_text="Resolvido pelo catálogo da origem quando a linha não traz.",
    )
    category = models.CharField("categoria", max_length=100, blank=True)
    qty = models.DecimalField("quantidade", max_digits=12, decimal_places=3)
    unit_price_q = models.BigIntegerField("preço unitário (centavos)")
    discount_q = models.BigIntegerField("desconto (centavos)", default=0)
    line_total_q = models.BigIntegerField("total da linha (centavos)")

    class Meta:
        verbose_name = "item de venda histórica"
        verbose_name_plural = "itens de venda histórica"
        ordering = ["sale", "seq"]
        constraints = [
            models.UniqueConstraint(fields=["sale", "seq"], name="backstage_histitem_sale_seq"),
        ]

    def __str__(self):
        return f"{self.product_name} ×{self.qty}"
