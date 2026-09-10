"""Resources do cofre — shop e packages do Core, com chave natural como identidade.

Três regras valem para todo resource daqui:

- **Chave natural como identidade de upsert** (``ref``/``sku``/``code``/``key``).
  Onde o modelo não tem chave natural (zonas de entrega, campanhas, conversões),
  o ``id`` entra na planilha e É a chave — e aí o restore preserva o id, o que
  mantém consistentes as FKs por id entre abas do mesmo arquivo.
- **Entidade com chave natural NÃO exporta ``id``**: um id de banco importado por
  cima de uma linha casada por ``ref`` trocaria a pk no save e duplicaria a
  linha em silêncio. FK e M2M atravessam a planilha pela chave natural do alvo.
- **Nada de usuário na planilha**: FKs para ``auth.User`` ficam de fora (o vault
  guarda curadoria, não contas), assim como ``uuid``/``created_at``/``updated_at``
  (regenerados ou automáticos).

``clean_model_instances = True`` roda ``full_clean()`` em cada linha importada —
choice inválido, valor fora de faixa e constraint violada falham ANTES do save,
com mensagem por linha, em vez de entrarem calados.
"""

from __future__ import annotations

from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget, ManyToManyWidget
from shopman.buyman.models import (
    Material,
    MaterialConversion,
    Supplier,
    SupplierMaterialCost,
)
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.guestman.models import PriceTier
from shopman.offerman.models import (
    Collection,
    CollectionItem,
    Listing,
    ListingItem,
    Product,
    ProductComponent,
)

from shopman.shop.backup import registry
from shopman.shop.models import (
    AnnouncementTemplate,
    Campaign,
    Channel,
    Coupon,
    DeliveryDistanceBand,
    DeliveryZone,
    NotificationTemplate,
    OmotenashiCopy,
    Promotion,
    QualityDefect,
    QualityGrade,
    RuleConfig,
    Shop,
)


#: Meta comum das entidades com chave natural: o id fica fora da planilha.
class NaturalKeyMeta:
    skip_unchanged = True
    report_skipped = True
    clean_model_instances = True
    exclude = ("id", "uuid", "created_at", "updated_at")


#: Meta das entidades sem chave natural: o id entra na planilha e é a chave.
class IdKeyMeta:
    skip_unchanged = True
    report_skipped = True
    clean_model_instances = True
    exclude = ("uuid", "created_at", "updated_at")
    import_id_fields = ("id",)


def _fk(model, natural_field: str, attribute: str) -> fields.Field:
    """FK que atravessa a planilha pela chave natural do alvo."""
    return fields.Field(
        column_name=f"{attribute}__{natural_field}",
        attribute=attribute,
        widget=ForeignKeyWidget(model, field=natural_field),
    )


# ---------------------------------------------------------------------------
# shop — a configuração curada do orquestrador
# ---------------------------------------------------------------------------


class ShopSettingsResource(resources.ModelResource):
    """A loja singleton — marca, endereço, horários, defaults de canal.

    ``integrations`` fica FORA de propósito: é onde moram chaves e segredos de
    gateway, e planilha de backup circula (Sheets, e-mail, pendrive). Segredo
    não entra em backup de curadoria — falhar fechado.
    """

    class Meta(IdKeyMeta):
        model = Shop
        exclude = IdKeyMeta.exclude + ("integrations",)


class ChannelResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = Channel
        import_id_fields = ("ref",)


class QualityGradeResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = QualityGrade
        import_id_fields = ("ref",)


class QualityDefectResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = QualityDefect
        import_id_fields = ("ref",)


class OmotenashiCopyResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = OmotenashiCopy
        import_id_fields = ("key", "moment", "audience")


class NotificationTemplateResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = NotificationTemplate
        import_id_fields = ("event",)


class AnnouncementTemplateResource(resources.ModelResource):
    class Meta(IdKeyMeta):
        model = AnnouncementTemplate


class CampaignResource(resources.ModelResource):
    template = fields.Field(
        column_name="template__id",
        attribute="template",
        widget=ForeignKeyWidget(AnnouncementTemplate, field="id"),
    )

    class Meta(IdKeyMeta):
        model = Campaign


class RuleConfigResource(resources.ModelResource):
    channels = fields.Field(
        column_name="channels__ref",
        attribute="channels",
        widget=ManyToManyWidget(Channel, field="ref", separator=","),
    )

    class Meta(NaturalKeyMeta):
        model = RuleConfig
        import_id_fields = ("ref",)


class PromotionResource(resources.ModelResource):
    channels = fields.Field(
        column_name="channels__ref",
        attribute="channels",
        widget=ManyToManyWidget(Channel, field="ref", separator=","),
    )

    class Meta(NaturalKeyMeta):
        model = Promotion
        import_id_fields = ("ref",)


class CouponResource(resources.ModelResource):
    promotion = _fk(Promotion, "ref", "promotion")

    class Meta(NaturalKeyMeta):
        model = Coupon
        import_id_fields = ("code",)


class DeliveryZoneResource(resources.ModelResource):
    class Meta(IdKeyMeta):
        model = DeliveryZone


class DeliveryDistanceBandResource(resources.ModelResource):
    class Meta(IdKeyMeta):
        model = DeliveryDistanceBand


# ---------------------------------------------------------------------------
# offerman — o catálogo
# ---------------------------------------------------------------------------


class TaggitField(fields.Field):
    """``keywords`` do produto como texto: 'pao, cafe-da-manha, integral'."""

    def __init__(self):
        super().__init__(column_name="keywords", attribute=None, readonly=False)

    def export(self, instance, **kwargs):
        return ", ".join(sorted(t.name for t in instance.keywords.all()))

    def save(self, instance, row, is_m2m=False, **kwargs):
        # A escrita real acontece em after_save_instance, com a instância salva.
        return None


class ProductBackupResource(resources.ModelResource):
    """Produto completo — inclui ``metadata`` (classificação fiscal, social PIM)
    e ``nutrition_facts``, que o resource de edição em massa do Admin não cobre.
    """

    keywords = TaggitField()

    class Meta(NaturalKeyMeta):
        model = Product
        import_id_fields = ("sku",)

    def after_save_instance(self, instance, row, **kwargs):
        if not kwargs.get("dry_run"):
            raw = row.get("keywords") or ""
            instance.keywords.set([t.strip() for t in raw.split(",") if t.strip()])


class ListingResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = Listing
        import_id_fields = ("ref",)


class ListingItemBackupResource(resources.ModelResource):
    """Diferente do resource de atualização de preço do Admin, aqui ``min_qty``
    faz parte da identidade — a mesma dupla listing×produto pode ter faixas de
    quantidade distintas, e o backup precisa devolver todas.
    """

    listing = _fk(Listing, "ref", "listing")
    product = _fk(Product, "sku", "product")

    class Meta(NaturalKeyMeta):
        model = ListingItem
        import_id_fields = ("listing", "product", "min_qty")


class CollectionResource(resources.ModelResource):
    parent = _fk(Collection, "ref", "parent")

    class Meta(NaturalKeyMeta):
        model = Collection
        import_id_fields = ("ref",)

    def get_queryset(self):
        """Pais antes de filhos na planilha — a linha do filho referencia o pai
        por ``ref``, e o import lê na ordem do arquivo."""
        remaining = {c.pk: c for c in super().get_queryset()}
        ordered: list[Collection] = []
        placed: set[int] = set()
        while remaining:
            progressed = False
            for pk, collection in list(remaining.items()):
                if collection.parent_id is None or collection.parent_id in placed:
                    ordered.append(remaining.pop(pk))
                    placed.add(pk)
                    progressed = True
            if not progressed:
                # Ciclo (não deveria existir): exporta o resto em ordem estável.
                ordered.extend(remaining.values())
                break
        return ordered


class CollectionItemResource(resources.ModelResource):
    collection = _fk(Collection, "ref", "collection")
    product = _fk(Product, "sku", "product")

    class Meta(NaturalKeyMeta):
        model = CollectionItem
        import_id_fields = ("collection", "product")


class ProductComponentResource(resources.ModelResource):
    parent = _fk(Product, "sku", "parent")
    component = _fk(Product, "sku", "component")

    class Meta(NaturalKeyMeta):
        model = ProductComponent
        import_id_fields = ("parent", "component")


# ---------------------------------------------------------------------------
# craftsman — as receitas (curadoria; WorkOrders são operação, não entram)
# ---------------------------------------------------------------------------


class RecipeResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = Recipe
        import_id_fields = ("ref",)


class RecipeItemResource(resources.ModelResource):
    recipe = _fk(Recipe, "ref", "recipe")

    class Meta(NaturalKeyMeta):
        model = RecipeItem
        import_id_fields = ("recipe", "input_sku")


# ---------------------------------------------------------------------------
# buyman — fornecedores, insumos, conversões e custos
# ---------------------------------------------------------------------------


class SupplierResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = Supplier
        import_id_fields = ("ref",)


class MaterialResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = Material
        import_id_fields = ("sku",)


class MaterialConversionResource(resources.ModelResource):
    """Conversões não têm chave natural completa (o rótulo só é único por par
    insumo×fornecedor, com fornecedor opcional) — o ``id`` é a chave, e por isso
    o restore preserva os ids que ``supplier_material_costs`` referencia.
    """

    material = _fk(Material, "sku", "material")
    supplier = _fk(Supplier, "ref", "supplier")

    class Meta(IdKeyMeta):
        model = MaterialConversion
        exclude = IdKeyMeta.exclude + ("created_by",)


class SupplierMaterialCostResource(resources.ModelResource):
    supplier = _fk(Supplier, "ref", "supplier")
    material = _fk(Material, "sku", "material")

    class Meta(NaturalKeyMeta):
        model = SupplierMaterialCost
        import_id_fields = ("supplier", "material")


# ---------------------------------------------------------------------------
# guestman — só a configuração (clientes são PII: LGPD, ficam no backup do banco)
# ---------------------------------------------------------------------------


class PriceTierResource(resources.ModelResource):
    class Meta(NaturalKeyMeta):
        model = PriceTier
        import_id_fields = ("ref",)


def register_shop_resources() -> None:
    """Registra as entidades do shop e dos packages do Core, em ordem de import."""
    for name, resource, tier in (
        ("shop_settings", ShopSettingsResource, 0),
        ("quality_grades", QualityGradeResource, 0),
        ("quality_defects", QualityDefectResource, 0),
        ("omotenashi_copy", OmotenashiCopyResource, 0),
        ("notification_templates", NotificationTemplateResource, 0),
        ("announcement_templates", AnnouncementTemplateResource, 0),
        ("products", ProductBackupResource, 0),
        ("materials", MaterialResource, 0),
        ("suppliers", SupplierResource, 0),
        ("price_tiers", PriceTierResource, 0),
        ("channels", ChannelResource, 1),
        ("listings", ListingResource, 1),
        ("collections", CollectionResource, 1),
        ("recipes", RecipeResource, 1),
        ("campaigns", CampaignResource, 1),
        ("material_conversions", MaterialConversionResource, 1),
        ("delivery_zones", DeliveryZoneResource, 1),
        ("delivery_bands", DeliveryDistanceBandResource, 1),
        ("rules", RuleConfigResource, 2),
        ("promotions", PromotionResource, 2),
        ("listing_items", ListingItemBackupResource, 2),
        ("collection_items", CollectionItemResource, 2),
        ("product_components", ProductComponentResource, 2),
        ("recipe_items", RecipeItemResource, 2),
        ("supplier_material_costs", SupplierMaterialCostResource, 2),
        ("coupons", CouponResource, 3),
    ):
        registry.register(name, resource, tier=tier)
