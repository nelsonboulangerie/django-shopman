"""Traz a Mercearia real para o catálogo: cria a revenda que a casa vende e troca os placeholders.

Usage::

    python manage.py apply_grocery_catalog            # ensaio: executa e desfaz
    python manage.py apply_grocery_catalog --apply    # grava

**Fonte.** A aba ``Produtos`` da planilha consolidada do dono (22–23/09/2026):
SKU no padrão de revenda ``TIPO-VARIANTE-MARCA-EMBALAGEM``, nome e preço do
Yooga, marca, GTIN, NCM e CEST das NF-e de compra. A tabela mora aqui, no
código, para que o banco novo (o ``seed`` chama :func:`apply_grocery`) e o banco
que já roda (este comando) terminem iguais.

**Entra quem tem dado para vender sem mentir**: nome, marca, embalagem, preço
maior que zero, NCM e GTIN que passa no dígito verificador GS1 (o validador
oficial do catálogo, ``gtin_is_valid``). Quem falta alguma dessas fica em
:data:`LEFT_OUT`, com o motivo — ausência declarada, não esquecimento.

**Como cada item nasce**

- Unidade ``un``; perfil fiscal ``own_production`` (CSOSN 102, CFOP 5102). O
  eixo do perfil é **ST × não-ST**, não "quem fabricou": ``own_production`` é
  "fabricação própria + revenda comum" (``fiscalman/classification.py``; o
  seed explica o mesmo para os chás Kãnfa). ⚠️ Por isso o **CEST não é
  gravado**: o perfil ``own_production`` o recusa ("CEST não se aplica"), e
  gravá-lo declararia uma ST que a casa não pratica hoje. O CEST da nota fica
  na tabela, para quando o contador disser se algum destes é ST.
- Marca e GTIN em ``metadata['social']`` (o que o feed e a página declaram) e
  o **cadastro de compra** do mesmo SKU (``buyman.Material``): é ele que torna
  o item comprável, e é por ele que o Compras recebe a NF-e (ver
  ``shopman/shop/services/sku_records.py``).
- Coleção ``mercearia``.
- **Despublicado** (``is_published=False``) e vendável, como os chás Kãnfa:
  alérgenos, tabela nutricional e ingredientes são dado da embalagem, que
  ninguém digitou ainda. Publicar é passo do gestor, depois da ficha.

**Onde se vende — a regra das listagens**

- **PDV sempre.** O balcão já vende estes itens hoje (é o histórico do Yooga);
  o PDV lê a listagem ``pdv``, não ``Product.is_published``.
- **Loja online, WhatsApp e iFood só com foto.** Sem foto nenhum item entra
  em canal onde o cliente compra de longe: ele decide pela imagem, e produto
  sem retrato na vitrine é produto que parece faltar. Nenhum item desta tabela
  tem foto hoje, então todos nascem só no PDV; quando a foto chegar
  (``image_url``), rodar o comando de novo os lista nos canais remotos. E o
  contrário também vale: item desta tabela sem foto que estiver num canal
  remoto sai dele.

**Placeholders da despensa que viram produto real** (:data:`REAL_PLACEHOLDERS`):
Ratatouille, Tapenade e Camembert tinham nome e preço provisórios do Cardápio
2027. O comando só troca quando o valor atual ainda é o placeholder — nome ou
preço que o gestor já mexeu fica, e sai no relatório como divergência. Os
outros placeholders (MT, QP, CX, BK, GR, LN, THL) esperam decisão do dono e não
estão aqui.

Idempotente: item que já está como a tabela diz não é tocado.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from shopman.shop.services.sku_records import ensure_purchase_record, sync_sale_listings

COLLECTION_REF = "mercearia"


@dataclass(frozen=True)
class GroceryItem:
    sku: str
    name: str
    price_q: int
    brand: str
    gtin: str
    ncm: str
    #: CEST da NF-e do fornecedor. NÃO é gravado (ver docstring do módulo).
    cest: str = ""
    #: Peso líquido da embalagem, em gramas. ``None`` quando ela é em volume.
    weight_g: int | None = None
    keywords: tuple[str, ...] = ()


#: Revenda real da Mercearia. Nome e preço: Yooga (preço mais praticado);
#: GTIN, NCM e CEST: NF-e de compra. Planilha consolidada, 22–23/09/2026.
GROCERY: tuple[GroceryItem, ...] = (
    # ── Azeite ──
    GroceryItem("AZEITE-DEFUMADO-MIRANTE-250", "Azeite Defumado Mirante 250ml", 14300, "Mirante",
                "602883466104", "15092000", "1706700", None, ("azeite", "defumado")),
    GroceryItem("AZEITE-DEFUMADO-PICANTE-MIRANTE-250", "Azeite Defumado Picante Mirante 250ml", 7700,
                "Mirante", "602883466128", "15092000", "1706700", None, ("azeite", "defumado", "picante")),
    # ── Conservas Duga ──
    GroceryItem("BERINJELA-DUGA-320", "Berinjela Insalata Duga 320g", 3100, "Duga",
                "7898655520010", "21039099", "1709200", 320, ("berinjela", "conserva", "antepasto")),
    GroceryItem("RELISH-ABOBRINHA-DUGA-320", "Relish de Abobrinha Duga 320g", 3100, "Duga",
                "7898655520065", "20019000", "1709000", 320, ("relish", "abobrinha", "conserva")),
    GroceryItem("RELISH-CEBOLA-DUGA-320", "Relish de Cebola Duga 320g", 3100, "Duga",
                "7898655520034", "20019000", "1709000", 320, ("relish", "cebola", "conserva")),
    GroceryItem("RELISH-PEPINO-DUGA-320", "Relish de Pepino Duga 320g", 3100, "Duga",
                "7898655520041", "20019000", "1709000", 320, ("relish", "pepino", "conserva")),
    # ── Cremes de queijo Pomerode ──
    GroceryItem("CREME-GORGONZOLA-POMERODE-90", "Creme de Gorgonzola Pomerode 90g", 2600, "Pomerode",
                "7898361661236", "04063000", "1702300", 90, ("queijo", "creme", "gorgonzola")),
    GroceryItem("CREME-PARMESAO-POMERODE-90", "Creme de Parmesão Kraeuterkaese Pomerode 90g", 2600,
                "Pomerode", "7898361661014", "04063000", "1702300", 90, ("queijo", "creme", "parmesao")),
    # ── Geleias St. Dalfour ──
    GroceryItem("GELEIA-DAMASCO-STDALFOUR-284", "Geleia Damasco St. Dalfour 284g", 4200, "St. Dalfour",
                "084380957543", "20079910", "1709400", 284, ("geleia", "damasco", "fruta")),
    GroceryItem("GELEIA-FIGO-STDALFOUR-284", "Geleia Figo St. Dalfour 284g", 4200, "St. Dalfour",
                "084380959042", "20079910", "1709400", 284, ("geleia", "figo", "fruta")),
    GroceryItem("GELEIA-FRUTASVERM-STDALFOUR-284", "Geleia Frutas Vermelhas St. Dalfour 284g", 4200,
                "St. Dalfour", "084380957840", "20079910", "1709400", 284, ("geleia", "frutas vermelhas", "fruta")),
    GroceryItem("GELEIA-LARANJA-STDALFOUR-284", "Geleia Laranja St. Dalfour 284g", 4200, "St. Dalfour",
                "084380957949", "20079100", "1709400", 284, ("geleia", "laranja", "fruta")),
    GroceryItem("GELEIA-LIMAO-STDALFOUR-284", "Geleia Limão St. Dalfour 284g", 4200, "St. Dalfour",
                "810019371295", "20079100", "1709400", 284, ("geleia", "limao", "fruta")),
    GroceryItem("GELEIA-MORANGO-STDALFOUR-284", "Geleia Morango St. Dalfour 284g", 4200, "St. Dalfour",
                "084380957444", "20079910", "1709400", 284, ("geleia", "morango", "fruta")),
    # Os dois minis nascem no lugar do `GL` (placeholder de sabor indefinido,
    # que o dono mandou sair em 22/09 — ver `apply_catalog_situacao`). O NCM do
    # de damasco veio da nota como 2007.99.90 e sem CEST; o de frutas
    # vermelhas, como os potes grandes.
    GroceryItem("GELEIA-DAMASCO-STDALFOUR-28", "Mini Geleia Damasco St. Dalfour 28g", 900, "St. Dalfour",
                "084380980428", "20079990", "", 28, ("geleia", "damasco", "fruta", "mini")),
    GroceryItem("GELEIA-FRUTASVERM-STDALFOUR-28", "Mini Geleia Frutas Vermelhas St. Dalfour 28g", 900,
                "St. Dalfour", "084380980626", "20079910", "1709400", 28,
                ("geleia", "frutas vermelhas", "fruta", "mini")),
    # ── Laticínios ──
    GroceryItem("MANTEIGA-SAL-PRESIDENT-200", "Manteiga Extra com Sal Président 200g", 1500, "Président",
                "3228020355741", "04051000", "1702500", 200, ("manteiga", "com sal")),
    GroceryItem("QUEIJO-BRIE-ILEDEFRANCE-25", "Queijo Mini Brie Ile de France 25g", 1000, "Ile de France",
                "3161712002113", "04069030", "1702400", 25, ("queijo", "brie", "mini")),
    # ── Mostardas Maille ──
    GroceryItem("MOSTARDA-MEL-MAILLE-215", "Mostarda com Mel Maille 215g", 4200, "Maille",
                "3036810204014", "21033021", "1703800", 215, ("mostarda", "mel")),
    GroceryItem("MOSTARDA-DIJON-MAILLE-215", "Mostarda Dijon Maille 215g", 3500, "Maille",
                "3036810201280", "21033021", "1703800", 215, ("mostarda", "dijon")),
    # ── Frios ──
    GroceryItem("PRESUNTO-CRU-VITOBAUDUCCI-100", "Presunto Cru Fatiado Vito Bauducci 100g", 3800,
                "Vito Bauducci", "7890203650002", "02101900", "1707904", 100, ("presunto", "cru", "fatiado")),
)

#: Mercearia da planilha que NÃO entra, e por quê. Entra quando o dado faltante
#: chegar — basta mover a linha para :data:`GROCERY`.
LEFT_OUT: dict[str, str] = {
    "QUEIJO-VALEDOTESTO-POMERODE": "preço zerado no Yooga e sem GTIN; sem preço não se vende",
    "CHURRASQUINHO-PIMENTA-MIRANTE-120": "sem GTIN: ler o código de barras da embalagem",
    "CREME-BRIE-POMERODE-90": "sem GTIN: ler o código de barras da embalagem",
    "MOSTARDA-ANCIENNE-MAILLE-210": "sem GTIN: ler o código de barras da embalagem",
    "CHA-CHALOSOFIA-KANFA-L50": "sem GTIN: não apareceu em nenhuma NF-e lida; ler o código de barras da lata",
    "CHA-VITAL-KANFA-L60": "sem GTIN: não apareceu em nenhuma NF-e lida; ler o código de barras da lata",
    "CHA-INTUICAO-KANFA-F250": "é INSUMO (lata de serviço do chá do bule), não produto de prateleira",
}


@dataclass(frozen=True)
class RealPlaceholder:
    """Placeholder do Cardápio 2027 que já tem o produto real do Yooga."""

    sku: str
    placeholder_name: str
    placeholder_price_q: int
    name: str
    price_q: int
    weight_g: int


REAL_PLACEHOLDERS: tuple[RealPlaceholder, ...] = (
    RealPlaceholder("RTAT", "Patê de Ratatouille", 2400, "Ratatouille 90g", 1800, 90),
    RealPlaceholder("TPND", "Tapenade", 2400, "Tapenade Azeitonas Pretas 100g", 2900, 100),
    RealPlaceholder("QUEIJO-CAMEMBERT-ILEDEFRANCE-125", "Camembert", 3800,
                    "Queijo Camembert Ile de France 125g", 4000, 125),
)


def _metadata(product) -> dict:
    return dict(product.metadata) if isinstance(product.metadata, dict) else {}


def _sync_listings(product, price_q: int, report: dict) -> None:
    """PDV sempre; canal remoto só com foto (``sku_records.sync_sale_listings``)."""
    from django.core.exceptions import ValidationError

    try:
        listed, unlisted = sync_sale_listings(product, price_q)
    except ValidationError as exc:
        raise CommandError(exc.messages[0]) from exc
    report["listed"].extend((product.sku, ref) for ref in listed)
    report["unlisted"].extend((product.sku, ref) for ref in unlisted)


def _ensure_collection(product, collection) -> None:
    from shopman.offerman.models import CollectionItem

    if CollectionItem.objects.filter(collection=collection, product=product).exists():
        return
    has_primary = CollectionItem.objects.filter(product=product, is_primary=True).exists()
    last = CollectionItem.objects.filter(collection=collection).order_by("-sort_order").first()
    CollectionItem.objects.create(
        collection=collection, product=product, is_primary=not has_primary,
        sort_order=(last.sort_order + 1) if last else 0,
    )


def _apply_item(item: GroceryItem, collection, report: dict) -> None:
    from shopman.offerman import get_social_attributes
    from shopman.offerman.contrib.social.schema import gtin_is_valid, set_social_attributes
    from shopman.offerman.models import AvailabilityPolicy, Product

    if item.price_q <= 0 or not gtin_is_valid(item.gtin):
        report["refused"].append((item.sku, "GTIN inválido" if item.price_q > 0 else "sem preço"))
        return

    product = Product.objects.filter(sku=item.sku).first()
    lines: list[str] = []
    if product is None:
        product = Product(
            sku=item.sku, name=item.name, base_price_q=item.price_q, unit="un",
            unit_weight_g=item.weight_g, is_published=False, is_sellable=True,
            availability_policy=AvailabilityPolicy.PLANNED_OK,
        )
        product.metadata = {"fiscal": {"profile": "own_production", "ncm": item.ncm, "unit": "UN"}}
        report["created"].append(item)
    else:
        for field, value in (("name", item.name), ("base_price_q", item.price_q)):
            have = getattr(product, field)
            if have != value:
                report["conflicts"].append((item.sku, field, have, value))

    metadata = _metadata(product)
    fiscal = dict(metadata.get("fiscal") or {})
    if not fiscal.get("ncm"):
        fiscal.update({"profile": fiscal.get("profile") or "own_production", "ncm": item.ncm, "unit": "UN"})
        lines.append(f"ncm: → {item.ncm}")
    elif fiscal["ncm"] != item.ncm:
        report["conflicts"].append((item.sku, "ncm", fiscal["ncm"], item.ncm))
    metadata["fiscal"] = fiscal

    product.metadata = metadata

    social = get_social_attributes(product)
    updates = {}
    for field, value in (("brand", item.brand), ("gtin", item.gtin)):
        have = getattr(social, field)
        if have == value:
            continue
        if have:
            report["conflicts"].append((item.sku, field, have, value))
            continue
        updates[field] = value
        lines.append(f"{field}: → {value}")
    if updates:
        product.metadata = set_social_attributes(product.metadata, replace(social, **updates))

    is_new = product.pk is None
    if is_new or lines:
        product.save()
        if not is_new:
            report["updated"].append((item.sku, lines))
    _material, purchasable = ensure_purchase_record(product)
    if purchasable and not is_new:
        report["updated"].append((item.sku, ["compra: cadastro de compra do mesmo SKU"]))
    product.keywords.add(COLLECTION_REF, *item.keywords)
    _ensure_collection(product, collection)
    _sync_listings(product, product.base_price_q, report)


def _apply_placeholder(real: RealPlaceholder, report: dict) -> None:
    from shopman.offerman.models import ListingItem, Product

    product = Product.objects.filter(sku=real.sku).first()
    if product is None:
        report["missing"].append(real.sku)
        return
    fields: list[str] = []
    lines: list[str] = []
    for field, placeholder, value in (
        ("name", real.placeholder_name, real.name),
        ("base_price_q", real.placeholder_price_q, real.price_q),
    ):
        have = getattr(product, field)
        if have == value:
            continue
        if have != placeholder:
            report["conflicts"].append((real.sku, field, have, value))
            continue
        setattr(product, field, value)
        fields.append(field)
        lines.append(f"{field}: {have!r} → {value!r}")
    if "name" in fields and product.unit_weight_g != real.weight_g:
        lines.append(f"peso: {product.unit_weight_g} g → {real.weight_g} g")
        product.unit_weight_g = real.weight_g
        fields.append("unit_weight_g")
    metadata = _metadata(product)
    if "base_price_q" in fields or (metadata.get("price_tbd") and product.base_price_q == real.price_q):
        if metadata.pop("price_tbd", None):
            lines.append("preço deixa de ser provisório")
            product.metadata = metadata
            fields.append("metadata")
    if not fields:
        return
    product.save(update_fields=[*fields, "updated_at"])
    if "base_price_q" in fields:
        # A listagem guarda o preço de cada canal: o PDV cobra o da listagem,
        # não o do produto. Só troca o que ainda era o placeholder.
        ListingItem.objects.filter(product=product, price_q=real.placeholder_price_q).update(price_q=real.price_q)
    report["updated"].append((real.sku, lines))


def apply_grocery(*, apply: bool) -> dict[str, list]:
    """Cria/atualiza a Mercearia real. Sem ``apply``, executa e desfaz.

    Chaves do relatório: ``created`` [GroceryItem], ``updated`` [(sku, linhas)],
    ``listed``/``unlisted`` [(sku, listagem)], ``conflicts`` [(sku, campo, atual,
    tabela)], ``refused`` [(sku, motivo)], ``missing`` [sku], ``left_out``
    [(sku, motivo)].
    """
    from shopman.offerman.models import Collection

    report: dict[str, list] = {
        "created": [], "updated": [], "listed": [], "unlisted": [], "conflicts": [],
        "refused": [], "missing": [], "left_out": sorted(LEFT_OUT.items()),
    }
    collection = Collection.objects.filter(ref=COLLECTION_REF).first()
    if collection is None:
        raise CommandError(f"A coleção `{COLLECTION_REF}` não existe neste banco.")

    with transaction.atomic():
        for item in GROCERY:
            _apply_item(item, collection, report)
        for real in REAL_PLACEHOLDERS:
            _apply_placeholder(real, report)
        if not apply:
            transaction.set_rollback(True)
    return report


class Command(BaseCommand):
    help = "Cria a revenda real da Mercearia (PDV; canal remoto só com foto) e troca os placeholders."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Grava. Sem isto o comando executa e desfaz, e só mostra o relatório.",
        )

    def handle(self, *args, apply: bool = False, **options):
        report = apply_grocery(apply=apply)
        out = self.stdout
        if report["created"]:
            verb = "Criados" if apply else "Criaria"
            out.write(self.style.SUCCESS(f"\n{verb} {len(report['created'])} produto(s) de Mercearia:"))
            for item in report["created"]:
                out.write(f"  {item.sku:38s} {item.name[:44]:44s} R$ {item.price_q / 100:6.2f}  {item.gtin}")
        for sku, lines in report["updated"]:
            out.write(f"  {sku:38s} {'; '.join(lines)}")
        listed = {}
        for sku, ref in report["listed"]:
            listed.setdefault(ref, []).append(sku)
        for ref, skus in sorted(listed.items()):
            out.write(f"  listagem {ref}: +{len(skus)}")
        for sku, ref in report["unlisted"]:
            out.write(self.style.WARNING(f"  {sku:38s} sai de {ref}: sem foto não se vende de longe"))
        for sku, field, have, want in report["conflicts"]:
            out.write(self.style.WARNING(f"  {sku:38s} {field} já é {have!r} (a tabela diz {want!r}) — mantido"))
        for sku, reason in report["refused"]:
            out.write(self.style.ERROR(f"  {sku:38s} recusado: {reason}"))
        if report["missing"]:
            out.write(self.style.WARNING(f"  fora do catálogo deste banco: {', '.join(report['missing'])}"))

        out.write(f"\nFicam de fora ({len(report['left_out'])}):")
        for sku, reason in report["left_out"]:
            out.write(f"  {sku:38s} {reason}")

        out.write(self.style.SUCCESS(
            f"\n{len(report['created'])} criado(s), {len(report['updated'])} atualizado(s), "
            f"{len(report['conflicts'])} divergência(s) mantida(s), {len(report['refused'])} recusado(s)."
        ))
        if not apply:
            out.write(self.style.WARNING("(ensaio: executado e desfeito, nada gravado. Para gravar: --apply)"))
