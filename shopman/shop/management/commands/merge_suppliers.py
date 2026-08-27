"""Funde dois cadastros do MESMO fornecedor num só.

**Por que este comando existe.** A mesma empresa entra no sistema por dois
caminhos que não se conhecem: o dono cadastra ``France Panificação`` pelo nome de
boca, e a primeira NF-e escaneada traz ``FRANCE PANIFICACAO LTDA`` como razão
social. Sem CNPJ no cadastro do dono, o casamento por documento não alcança, e
nascem dois fornecedores para uma empresa — com o histórico de custo partido ao
meio.

O ``_adopt_supplier_by_name`` (em ``shopman/backstage/services/purchase.py``)
impede que isso volte a acontecer. Este comando resolve o que já aconteceu.

Uso::

    python manage.py merge_suppliers ORIGEM DESTINO        # só mostra o que faria
    python manage.py merge_suppliers ORIGEM DESTINO --apply

A ORIGEM desaparece; o DESTINO fica com tudo. Prefira como DESTINO o cadastro que
o seed recria (ex.: ``france-panificacao``), porque ele sobrevive a
``seed --flush``; o que veio da NF é recriado do zero a cada nota nova.

O que se move:

- ``SupplierMaterialCost`` e ``MaterialConversion`` — repontados para o destino.
  Em colisão (o destino já tem custo/conversão para aquele insumo), o do destino
  vence e o da origem é descartado: dois registros para o mesmo par violariam a
  unicidade, e o destino é quem o operador escolheu manter.
- ``Material.metadata`` — ``supplier`` e ``alt_suppliers`` passam a apontar para o
  destino, sem duplicar a entrada.
- ``Move.metadata.purchase_supplier_ref`` — o histórico de entrada passa a
  apontar para o destino, senão a última entrega do fornecedor some da tela.
- ``Supplier.metadata.purchase.invoice_product_map`` — o de-para NF→insumo
  aprendido (PR #352) é somado; em conflito de chave, o do destino vence.
- ``document`` e ``phone`` — copiados da origem só se o destino estiver vazio.
  Nunca sobrescreve dado do destino.
"""

from __future__ import annotations

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Funde dois cadastros do mesmo fornecedor (a origem desaparece no destino)."

    def add_arguments(self, parser):
        parser.add_argument("origem", help="ref do fornecedor que vai desaparecer")
        parser.add_argument("destino", help="ref do fornecedor que fica com tudo")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Executa. Sem esta flag o comando só relata o que faria.",
        )

    def handle(self, *args, **options):
        origem_ref = options["origem"]
        destino_ref = options["destino"]
        aplicar = options["apply"]

        if origem_ref == destino_ref:
            raise CommandError("Origem e destino são o mesmo fornecedor.")

        Supplier = apps.get_model("buyman", "Supplier")
        origem = Supplier.objects.filter(ref=origem_ref).first()
        destino = Supplier.objects.filter(ref=destino_ref).first()
        if origem is None:
            raise CommandError(f"Fornecedor de origem não encontrado: {origem_ref}")
        if destino is None:
            raise CommandError(f"Fornecedor de destino não encontrado: {destino_ref}")

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n{origem.name} ({origem.ref})  →  {destino.name} ({destino.ref})\n"
            )
        )

        with transaction.atomic():
            relatorio = self._merge(origem, destino)
            for linha in relatorio:
                self.stdout.write(f"  {linha}")
            if not aplicar:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.WARNING("\n  ⚠️  Ensaio — nada foi gravado. Repita com --apply.\n")
                )
                return
        self.stdout.write(self.style.SUCCESS(f"\n  ✅ {origem_ref} fundido em {destino_ref}\n"))

    # ────────────────────────────────────────────────────────────────────
    def _merge(self, origem, destino) -> list[str]:
        relatorio: list[str] = []
        relatorio += self._mover_custos(origem, destino)
        relatorio += self._mover_conversoes(origem, destino)
        relatorio += self._repontar_materiais(origem, destino)
        relatorio += self._repontar_movimentos(origem, destino)
        relatorio += self._fundir_metadata(origem, destino)
        origem.delete()
        relatorio.append(f"cadastro {origem.ref} apagado")
        return relatorio

    def _mover_custos(self, origem, destino) -> list[str]:
        Cost = apps.get_model("buyman", "SupplierMaterialCost")
        movidos = descartados = 0
        for custo in Cost.objects.filter(supplier=origem):
            if Cost.objects.filter(supplier=destino, material_id=custo.material_id).exists():
                custo.delete()
                descartados += 1
            else:
                custo.supplier = destino
                custo.save(update_fields=["supplier", "updated_at"])
                movidos += 1
        return [f"custos: {movidos} movidos, {descartados} descartados (destino já tinha)"]

    def _mover_conversoes(self, origem, destino) -> list[str]:
        Conversion = apps.get_model("buyman", "MaterialConversion")
        movidas = descartadas = 0
        for conv in Conversion.objects.filter(supplier=origem):
            colide = Conversion.objects.filter(
                supplier=destino, material_id=conv.material_id, label=conv.label
            ).exists()
            if colide:
                conv.delete()
                descartadas += 1
            else:
                conv.supplier = destino
                conv.save(update_fields=["supplier", "updated_at"])
                movidas += 1
        return [f"conversões: {movidas} movidas, {descartadas} descartadas (destino já tinha)"]

    def _repontar_materiais(self, origem, destino) -> list[str]:
        Material = apps.get_model("buyman", "Material")
        tocados = 0
        for material in Material.objects.all():
            metadata = dict(material.metadata or {})
            mudou = False
            if metadata.get("supplier") == origem.ref:
                metadata["supplier"] = destino.ref
                mudou = True
            alternativos = metadata.get("alt_suppliers")
            if isinstance(alternativos, list):
                # Normaliza SEMPRE, não só quando a origem aparece: se o destino já
                # era alternativo deste insumo, depois da fusão ele ficaria listado
                # como alternativa de si mesmo — que é a bagunça que a fusão
                # deveria justamente resolver.
                principal = metadata.get("supplier")
                novos: list[str] = []
                for ref in alternativos:
                    ref = destino.ref if ref == origem.ref else ref
                    if ref and ref != principal and ref not in novos:
                        novos.append(ref)
                if novos != alternativos:
                    metadata["alt_suppliers"] = novos
                    mudou = True
            if mudou:
                material.metadata = metadata
                material.save(update_fields=["metadata", "updated_at"])
                tocados += 1
        return [f"insumos repontados: {tocados}"]

    def _repontar_movimentos(self, origem, destino) -> list[str]:
        Move = apps.get_model("stockman", "Move")
        tocados = 0
        for move in Move.objects.filter(metadata__purchase_supplier_ref=origem.ref):
            metadata = dict(move.metadata or {})
            metadata["purchase_supplier_ref"] = destino.ref
            move.metadata = metadata
            move.save(update_fields=["metadata"])
            tocados += 1
        return [f"movimentos de entrada repontados: {tocados}"]

    def _fundir_metadata(self, origem, destino) -> list[str]:
        relatorio: list[str] = []
        campos = []

        if not (destino.document or "").strip() and (origem.document or "").strip():
            destino.document = origem.document
            campos.append("document")
        if not (destino.phone or "").strip() and (origem.phone or "").strip():
            destino.phone = origem.phone
            campos.append("phone")

        metadata = dict(destino.metadata or {})
        purchase = dict(metadata.get("purchase") or {})
        origem_purchase = dict((origem.metadata or {}).get("purchase") or {})
        mapa_origem = dict(origem_purchase.get("invoice_product_map") or {})
        mapa_destino = dict(purchase.get("invoice_product_map") or {})
        somados = 0
        for chave, valor in mapa_origem.items():
            if chave not in mapa_destino:
                mapa_destino[chave] = valor
                somados += 1
        if mapa_destino:
            purchase["invoice_product_map"] = mapa_destino
            metadata["purchase"] = purchase
            destino.metadata = metadata
            campos.append("metadata")

        if campos:
            destino.save(update_fields=[*dict.fromkeys(campos), "updated_at"])
        relatorio.append(
            f"de-para NF→insumo: {somados} chaves somadas ({len(mapa_destino)} no total)"
        )
        relatorio.append(
            "campos herdados da origem: " + (", ".join(campos) if campos else "nenhum")
        )
        return relatorio
