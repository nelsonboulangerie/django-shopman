"""Importa versões de receita de um arquivo JSON para o inventário (WP-RECEITAS-DO-DONO §C.7).

Os valores NÃO moram no repositório: o arquivo é gerado na hora, a partir da
planilha do dono, e passado por caminho. Para cada receita do arquivo:

- cria uma versão nova (``create_version``) na ``RecipeEntry`` que já existe, com
  ``source = {"kind": "import", "text": <source_text>}``, ``origin`` = o bloco
  como está na planilha, ``formula`` em grama, rendimento = a linha Total
  convertida para grama, ``steps`` vazio e o ``label`` do arquivo;
- uma linha que é parte (o levain) entra em ``parts``, e o que ela carrega
  (farinha, água, cultura) entra na fórmula base pela composição da parte: a do
  próprio arquivo quando a parte também é importada, senão a versão atual dela;
- ``autolyse`` (opcional) passa TODA a farinha da mistura final pela parte
  autolisada que já existe (ex.: Pasta Autolizada), e a água que a pasta leva sai
  da água da mistura final. Só quando a conta fecha exata (três casas, sem
  arredondar) e cabe na água da planilha; senão a receita fica em rascunho, sem
  publicar, e o motivo é dito.

Sem ``--apply`` só mostra o plano. ``--apply`` grava os rascunhos; com
``--publish`` também publica (``publish``), na ordem das dependências: a parte
antes de quem a consome. A versão publicada antes fica "Substituída".
Idempotente: rascunho igual é reaproveitado, versão igual já publicada é pulada.

Formato do arquivo::

    {
      "source_text": "ANÁLISE_CUSTOS_CVL_2021, aba Fx",
      "label": "Fórmula da Fx",
      "recipes": [
        {
          "entry_ref": "creme-levain",
          "title": "LEVAIN",
          "lines": [
            {"name": "<como a planilha escreve>", "quantity": "0.5", "unit": "kg", "sku": "FARINHA-NOVARA-T55"},
            {"name": "LEVAIN", "quantity": "0.1", "unit": "kg",
             "part": {"sku": "LEVAIN", "entry_ref": "creme-levain", "kind": "preferment"}}
          ],
          "total": {"quantity": "3", "unit": "kg"},
          "autolyse": {"sku": "PASTA-AUTOLIZADA", "entry_ref": "massa-pasta-autolizada"},
          "notes": ""
        }
      ]
    }

Uso:
    python manage.py import_recipe_versions /caminho/receitas.json
    python manage.py import_recipe_versions /caminho/receitas.json --apply
    python manage.py import_recipe_versions /caminho/receitas.json --apply --publish
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from shopman.craftsman.contrib.formula.percentages import (
    PART_KINDS,
    analyze,
    classify_ingredient,
    item_grams,
    number_text,
    quantize,
    to_decimal,
)

_GRAMS = {"kg": Decimal(1000), "g": Decimal(1)}
_ZERO = Decimal(0)


@dataclass
class Plan:
    entry_ref: str
    formula: dict
    yield_g: Decimal
    origin: dict
    notes: str
    depends_on: list[str] = field(default_factory=list)
    hold: str = ""
    part_formulas: dict[str, dict] = field(default_factory=dict)


class Command(BaseCommand):
    help = "Importa versões de receita de um JSON (sem --apply só mostra; --publish publica na ordem)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Arquivo JSON gerado na hora (nunca versionado).")
        parser.add_argument("--apply", action="store_true", help="Grava os rascunhos.")
        parser.add_argument("--publish", action="store_true", help="Com --apply: publica na ordem das dependências.")
        parser.add_argument("--actor", default="import_recipe_versions", help="Quem publica (vai para o meta da versão).")

    def handle(self, *args, **options):
        from shopman.craftsman.models import RecipeEntry

        if options["publish"] and not options["apply"]:
            raise CommandError("--publish só vale junto com --apply.")
        try:
            spec = json.loads(Path(options["path"]).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CommandError(f"Não consegui ler o arquivo: {exc}") from exc
        source_text = str(spec.get("source_text") or "").strip()
        label = str(spec.get("label") or "").strip()
        recipes = list(spec.get("recipes") or [])
        if not source_text or not label or not recipes:
            raise CommandError("O arquivo precisa de source_text, label e recipes.")

        refs = [str(r.get("entry_ref") or "").strip() for r in recipes]
        missing = sorted(set(refs) - set(RecipeEntry.objects.filter(ref__in=refs).values_list("ref", flat=True)))
        if missing:
            raise CommandError(f"Receita inexistente no inventário: {', '.join(missing)}.")

        plans: dict[str, Plan] = {}
        for recipe in _dependency_order(recipes):
            plan = _build_plan(recipe, plans)
            plans[plan.entry_ref] = plan

        source = {"kind": "import", "text": source_text}
        with transaction.atomic():
            for plan in plans.values():
                self._run(plan, plans, label=label, source=source, options=options)
            if not options["apply"]:
                transaction.set_rollback(True)
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Só o plano: nada gravado (use --apply)."))

    # ── execução ─────────────────────────────────────────────────────────────

    def _run(self, plan: Plan, plans: dict[str, Plan], *, label: str, source: dict, options: dict) -> None:
        from shopman.craftsman.models import RecipeEntry, RecipeVersion
        from shopman.craftsman.services import recipe_book as craftsman

        from shopman.backstage.services import recipe_book as service

        entry = RecipeEntry.objects.select_related("current_version").get(ref=plan.entry_ref)
        current = entry.current_version
        self.stdout.write(f"\n{entry.ref} ({entry.output_sku}), atual: "
                          f"{current.version_ref + ' ' + repr(current.label) if current else 'nenhuma'}")
        analysis = analyze(plan.formula, plan.part_formulas)
        for line in analysis.bom:
            self.stdout.write(f"    {line['sku']:<36} {number_text(line['quantity']):>10} {line['unit']}")
        self.stdout.write(f"    rendimento {number_text(plan.yield_g)} g")
        for warning in analysis.warnings:
            self.stdout.write(f"    aviso {warning.code}: {warning.message}")
        if plan.hold:
            self.stdout.write(self.style.WARNING(f"    fica em RASCUNHO: {plan.hold}"))

        same = [
            v for v in entry.versions.filter(label=label).order_by("-number")
            if (v.source or {}).get("kind") == "import" and (v.source or {}).get("text") == source["text"]
            and v.formula == plan.formula and v.yield_quantity == quantize(plan.yield_g) and v.yield_unit == "g"
        ]
        published = next((v for v in same if v.status == RecipeVersion.Status.PUBLISHED), None)
        if published is not None:
            self.stdout.write(f"    já publicada: {published.version_ref}")
            return
        draft = next((v for v in same if v.status == RecipeVersion.Status.DRAFT), None)
        if draft is None:
            self.stdout.write(f"    {'cria' if options['apply'] else 'criaria'} rascunho v{_next_number(entry)}")
            draft = craftsman.create_version(
                entry, formula=plan.formula, yield_quantity=plan.yield_g, yield_unit="g",
                origin=plan.origin, source=source, steps=[], notes=plan.notes, label=label,
                created_by=options["actor"],
            )
        else:
            self.stdout.write(f"    rascunho igual já existe: {draft.version_ref}")

        if not options["publish"] or plan.hold:
            return
        for dep in plan.depends_on:
            dep_entry = RecipeEntry.objects.select_related("current_version").get(ref=dep)
            if dep_entry.current_version is None or dep_entry.current_version.formula != plans[dep].formula:
                self.stdout.write(self.style.WARNING(f"    não publica: a parte {dep} não está publicada com esta fórmula"))
                return
        service.publish(draft, actor=options["actor"])
        draft.refresh_from_db()
        self.stdout.write(self.style.SUCCESS(f"    publicada: {draft.version_ref}"))


def _next_number(entry) -> int:
    return (entry.versions.order_by("-number").values_list("number", flat=True).first() or 0) + 1


def _dependency_order(recipes: list[dict]) -> list[dict]:
    """Quem é parte de outra receita do arquivo vem antes dela."""
    by_ref = {str(r.get("entry_ref") or "").strip(): r for r in recipes}
    ordered: list[dict] = []
    seen: set[str] = set()

    def visit(ref: str, stack: tuple[str, ...]) -> None:
        if ref in seen:
            return
        if ref in stack:
            raise CommandError(f"Dependência circular entre receitas: {' → '.join((*stack, ref))}.")
        for line in by_ref[ref].get("lines") or []:
            dep = str((line.get("part") or {}).get("entry_ref") or "").strip()
            if dep and dep in by_ref and dep != ref:
                visit(dep, (*stack, ref))
        seen.add(ref)
        ordered.append(by_ref[ref])

    for ref in by_ref:
        visit(ref, ())
    return ordered


# ── a fórmula ────────────────────────────────────────────────────────────────


def _grams(quantity, unit: str, where: str) -> Decimal:
    value = to_decimal(quantity)
    factor = _GRAMS.get(str(unit or "").strip())
    if value is None or value <= 0 or factor is None:
        raise CommandError(f"{where}: quantidade/unidade inválida ({quantity!r} {unit!r}); use kg ou g.")
    return value * factor


def _material_name(sku: str, fallback: str) -> str:
    from shopman.buyman.models import Material

    return Material.objects.filter(sku=sku).values_list("name", flat=True).first() or fallback


def _current_formula(entry_ref: str) -> dict:
    from shopman.craftsman.models import RecipeEntry

    entry = RecipeEntry.objects.select_related("current_version").filter(ref=entry_ref).first()
    if entry is None or entry.current_version is None:
        raise CommandError(f"A parte {entry_ref} não tem versão publicada.")
    return entry.current_version.formula or {}


def _composition(formula: dict, where: str) -> list[tuple[str, str, Decimal]]:
    """(sku, nome, grama) de cada item da fórmula; a parte precisa ser só insumo."""
    if formula.get("parts"):
        raise CommandError(f"{where}: a composição da parte tem sub-partes; este comando não desce mais um nível.")
    out = []
    for item in formula.get("items") or []:
        grams = item_grams(item)
        sku = str(item.get("sku") or "").strip()
        if grams is None or not sku:
            raise CommandError(f"{where}: item sem SKU ou sem peso na composição da parte.")
        out.append((sku, str(item.get("name") or sku), grams))
    return out


def _build_plan(recipe: dict, plans: dict[str, Plan]) -> Plan:
    from shopman.craftsman.models import RecipeEntry
    from shopman.craftsman.services.recipe_book import suggest_anchor_kind

    ref = str(recipe.get("entry_ref") or "").strip()
    entry = RecipeEntry.objects.get(ref=ref)
    base: dict[str, dict] = {}
    final_g: dict[str, Decimal] = {}
    parts: list[dict] = []
    part_formulas: dict[str, dict] = {}
    depends_on: list[str] = []
    origin_lines: list[dict] = []

    def add(sku: str, name: str, grams: Decimal) -> None:
        if sku in base:
            base[sku]["grams"] += grams
        else:
            base[sku] = {"sku": sku, "name": _material_name(sku, name), "grams": grams}

    for index, line in enumerate(recipe.get("lines") or []):
        where = f"{ref}, linha {index + 1}"
        name = str(line.get("name") or "").strip()
        unit = str(line.get("unit") or "").strip()
        grams = _grams(line.get("quantity"), unit, where)
        origin_lines.append({"name": name, "quantity": str(line.get("quantity")), "unit": unit})
        part = line.get("part")
        if part:
            part_sku = str(part.get("sku") or "").strip()
            part_ref = str(part.get("entry_ref") or "").strip()
            kind = str(part.get("kind") or "preferment")
            if not part_sku or not part_ref or kind not in PART_KINDS or kind == "old_dough":
                raise CommandError(f"{where}: parte precisa de sku, entry_ref e kind válido.")
            if part_ref in plans:
                part_formula = plans[part_ref].formula
                depends_on.append(part_ref)
            else:
                part_formula = _current_formula(part_ref)
            composition = _composition(part_formula, where)
            total = sum((g for _, _, g in composition), _ZERO)
            for sku, comp_name, comp_g in composition:
                add(sku, comp_name, comp_g / total * grams)
            part_formulas[part_sku] = part_formula
            parts.append({"sku": part_sku, "entry_ref": part_ref, "kind": kind, "name": name,
                          "quantity": number_text(grams), "unit": "g", "flour_pct": None})
            continue
        sku = str(line.get("sku") or "").strip()
        if not sku:
            raise CommandError(f"{where}: ingrediente sem SKU ({name!r}).")
        add(sku, name, grams)
        final_g[sku] = final_g.get(sku, _ZERO) + grams

    hold = ""
    autolyse = recipe.get("autolyse")
    if autolyse:
        hold = _autolyse(autolyse, ref, final_g, parts, part_formulas)

    items = []
    for line in base.values():
        role = classify_ingredient(line["name"], line["sku"])
        items.append({"sku": line["sku"], "name": line["name"], "quantity": number_text(line["grams"]),
                      "unit": "g", "role": role})
    flour = sum((to_decimal(i["quantity"]) for i in items if i["role"] == "flour"), _ZERO)
    mass = sum((to_decimal(i["quantity"]) for i in items), _ZERO)
    formula = {
        "anchor": {"kind": suggest_anchor_kind(flour, mass, entry.kind)},
        "basis_g": None,
        "standardized": False,
        "items": items,
        "parts": parts,
    }
    total = recipe.get("total") or {}
    yield_g = _grams(total.get("quantity"), total.get("unit"), f"{ref}, total")
    origin = {
        "title": str(recipe.get("title") or ""),
        "lines": origin_lines,
        "total": {"quantity": str(total.get("quantity")), "unit": str(total.get("unit"))},
    }
    return Plan(entry_ref=ref, formula=formula, yield_g=yield_g, origin=origin,
                notes=str(recipe.get("notes") or ""), depends_on=depends_on, hold=hold,
                part_formulas=part_formulas)


def _autolyse(spec: dict, ref: str, final_g: dict[str, Decimal], parts: list[dict],
              part_formulas: dict[str, dict]) -> str:
    """Passa toda a farinha da mistura final pela parte autolisada; devolve o motivo se não fecha exato."""
    sku = str(spec.get("sku") or "").strip()
    entry_ref = str(spec.get("entry_ref") or "").strip()
    if not sku or not entry_ref:
        raise CommandError(f"{ref}: autolyse precisa de sku e entry_ref.")
    composition = _composition(_current_formula(entry_ref), f"{ref}, autolyse")
    roles = {s: classify_ingredient(n, s) for s, n, _ in composition}
    flours = [s for s, r in roles.items() if r == "flour"]
    liquids = [s for s, r in roles.items() if r == "liquid"]
    if len(flours) != 1 or len(liquids) != 1 or len(composition) != 2:
        return f"a {entry_ref} não é só uma farinha e uma água"
    flour_sku, water_sku = flours[0], liquids[0]
    comp = {s: g for s, _, g in composition}
    total = sum(comp.values(), _ZERO)
    if flour_sku not in final_g or water_sku not in final_g:
        return f"a mistura final não tem {flour_sku} e {water_sku}, que a {entry_ref} leva"
    paste_g = final_g[flour_sku] * total / comp[flour_sku]
    water_g = paste_g * comp[water_sku] / total
    if paste_g != quantize(paste_g) or water_g != quantize(water_g):
        return f"a farinha da planilha não vira {entry_ref} sem arredondar"
    if water_g > final_g[water_sku]:
        return f"a {entry_ref} pede mais água do que a planilha tem na mistura final"
    from shopman.craftsman.models import RecipeEntry

    name = RecipeEntry.objects.filter(ref=entry_ref).values_list("name", flat=True).first() or sku
    parts.insert(0, {"sku": sku, "entry_ref": entry_ref, "kind": "autolyse", "name": name,
                     "quantity": number_text(paste_g), "unit": "g", "flour_pct": None})
    part_formulas[sku] = _current_formula(entry_ref)
    return ""
