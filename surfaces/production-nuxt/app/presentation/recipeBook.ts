// Presentation — inventário de receitas (RECIPE-INVENTORY-PLAN §9). Transforms
// puras sobre o contrato de shopman/backstage/projections/recipe_book.py. A conta
// oficial (porcentagem do padeiro, hidratação, mistura final, BOM) é da LENTE do
// servidor; aqui só há o que a tela precisa antes da resposta chegar: rótulos,
// filtros, edição imutável da fórmula, um percentual de feedback imediato do
// editor e a matemática do tamanho-alvo da foto (o canvas fica no composable).
import type {
  AnchorKind,
  CaptureItemProjection,
  Formula,
  FormulaItem,
  FormulaItemProjection,
  FormulaPart,
  FormulaUnit,
  IngredientRole,
  LensTone,
  PartKind,
  RecipeCaptureDraftProjection,
  RecipeEntryCardProjection,
  RecipeKind,
  VersionStatus,
} from "~/types/recipeBook";

// ── Vocabulário (rótulos em pt-BR; identificador em inglês) ─────────────────

export const ROLE_OPTIONS: readonly { value: IngredientRole; label: string }[] = [
  { value: "flour", label: "Farinha" },
  { value: "liquid", label: "Líquido" },
  { value: "salt", label: "Sal" },
  { value: "yeast", label: "Fermento" },
  { value: "fat", label: "Gordura" },
  { value: "sugar", label: "Açúcar" },
  { value: "egg", label: "Ovos" },
  { value: "dairy", label: "Laticínio" },
  { value: "inclusion", label: "Inclusão" },
  { value: "other", label: "Outro" },
] as const;

export function roleLabel(role: string): string {
  return ROLE_OPTIONS.find((entry) => entry.value === role)?.label ?? "Outro";
}

export const KIND_OPTIONS: readonly { value: RecipeKind; label: string }[] = [
  { value: "bread", label: "Pão" },
  { value: "viennoiserie", label: "Viennoiserie" },
  { value: "sweet_dough", label: "Massa doce" },
  { value: "filling", label: "Recheio" },
  { value: "cream", label: "Creme" },
  { value: "sauce", label: "Molho" },
  { value: "beverage", label: "Bebida" },
  { value: "other", label: "Outra" },
] as const;

export function kindLabel(kind: string): string {
  return KIND_OPTIONS.find((entry) => entry.value === kind)?.label ?? "Outra";
}

export const PART_KIND_OPTIONS: readonly { value: PartKind; label: string }[] = [
  { value: "preferment", label: "Pré-fermento" },
  { value: "autolyse", label: "Autólise" },
  { value: "soaker", label: "Grãos hidratados" },
  { value: "old_dough", label: "Massa velha" },
] as const;

export function partKindLabel(kind: string): string {
  return PART_KIND_OPTIONS.find((entry) => entry.value === kind)?.label ?? kind;
}

export const ANCHOR_OPTIONS: readonly { value: AnchorKind; label: string }[] = [
  { value: "flour", label: "Farinhas totais" },
  { value: "total", label: "Massa total" },
  { value: "ingredient", label: "Um ingrediente" },
] as const;

export function anchorLabel(kind: string): string {
  return ANCHOR_OPTIONS.find((entry) => entry.value === kind)?.label ?? kind;
}

export const UNIT_OPTIONS: readonly FormulaUnit[] = ["g", "kg", "ml", "L", "un"] as const;
export const YIELD_UNIT_OPTIONS: readonly string[] = ["kg", "g", "un", "L", "ml"] as const;

/** Padrão da casa: a âncora soma 1000 g (§3). */
export const HOUSE_BASIS_G = 1000;

// ── Tom ────────────────────────────────────────────────────────────────────

export function statusTone(status: string): LensTone {
  if (status === "draft") return "warning";
  if (status === "published") return "ok";
  return "muted";
}

export function statusBadgeVariant(status: string): "success" | "warning" | "outline" {
  const tone = statusTone(status as VersionStatus);
  if (tone === "ok") return "success";
  if (tone === "warning") return "warning";
  return "outline";
}

/** Classes tonais de um chip/valor: calmo por padrão; só o aviso carrega cor. */
export function toneClass(tone: string): string {
  switch (tone) {
    case "warning":
      return "text-amber-700 dark:text-amber-300";
    case "ok":
      return "text-foreground";
    default:
      return "text-muted-foreground";
  }
}

/** Classes de um chip de métrica/aviso (borda + fundo + texto). */
export function toneChip(tone: string): string {
  switch (tone) {
    case "warning":
      return "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "ok":
      return "border-border bg-card text-foreground";
    default:
      return "border-border bg-muted text-muted-foreground";
  }
}

// ── Referência de versão (`<ref>@<n>`) ──────────────────────────────────────

export function versionRefLabel(ref: string, number: number): string {
  return `${ref}@${number}`;
}

export function parseVersionRef(value: string): { ref: string; number: number } | null {
  const at = value.lastIndexOf("@");
  if (at <= 0) return null;
  const ref = value.slice(0, at);
  const number = Number(value.slice(at + 1));
  if (!ref || !Number.isInteger(number) || number < 1) return null;
  return { ref, number };
}

// ── Fórmula vazia e edição imutável ─────────────────────────────────────────

export function emptyFormula(anchorKind: AnchorKind = "flour", anchorSku = ""): Formula {
  return {
    anchor: anchorKind === "ingredient" ? { kind: "ingredient", sku: anchorSku } : { kind: anchorKind },
    basis_g: null,
    standardized: false,
    items: [],
    parts: [],
  };
}

export function emptyItem(over: Partial<FormulaItem> = {}): FormulaItem {
  return { sku: "", name: "", role: "other", quantity: 0, unit: "g", note: "", ...over };
}

export function emptyPart(kind: PartKind = "preferment"): FormulaPart {
  if (kind === "old_dough") return { kind, cap_pct: 20 };
  return { kind, sku: "", entry_ref: "", flour_pct: null, quantity: null, unit: "g" };
}

export function addItem(formula: Formula, item: FormulaItem = emptyItem()): Formula {
  return { ...formula, items: [...formula.items, item] };
}

export function updateItem(formula: Formula, index: number, patch: Partial<FormulaItem>): Formula {
  if (index < 0 || index >= formula.items.length) return formula;
  return {
    ...formula,
    items: formula.items.map((item, i) => (i === index ? { ...item, ...patch } : item)),
  };
}

export function removeItem(formula: Formula, index: number): Formula {
  if (index < 0 || index >= formula.items.length) return formula;
  return { ...formula, items: formula.items.filter((_, i) => i !== index) };
}

export function moveItem(formula: Formula, from: number, to: number): Formula {
  const last = formula.items.length - 1;
  if (from < 0 || from > last || to < 0 || to > last || from === to) return formula;
  const items = [...formula.items];
  const [moved] = items.splice(from, 1);
  items.splice(to, 0, moved as FormulaItem);
  return { ...formula, items };
}

export function addPart(formula: Formula, part: FormulaPart = emptyPart()): Formula {
  return { ...formula, parts: [...formula.parts, part] };
}

export function updatePart(formula: Formula, index: number, patch: Partial<FormulaPart>): Formula {
  if (index < 0 || index >= formula.parts.length) return formula;
  return {
    ...formula,
    parts: formula.parts.map((part, i) => (i === index ? { ...part, ...patch } : part)),
  };
}

export function removePart(formula: Formula, index: number): Formula {
  if (index < 0 || index >= formula.parts.length) return formula;
  return { ...formula, parts: formula.parts.filter((_, i) => i !== index) };
}

export function setAnchor(formula: Formula, kind: AnchorKind, sku = ""): Formula {
  return {
    ...formula,
    anchor: kind === "ingredient" ? { kind, sku } : { kind },
  };
}

/** Há farinha na fórmula? Sugere a âncora `flour` (a lente vem do conteúdo, §1). */
export function formulaHasFlour(formula: Formula): boolean {
  return formula.items.some((item) => item.role === "flour");
}

export function suggestedAnchor(formula: Formula): AnchorKind {
  return formulaHasFlour(formula) ? "flour" : "total";
}

// ── Feedback imediato do editor (a conta oficial é a lente do servidor) ─────

/** Gramas aproximados de um item para a prévia local. Volume assume 1,0 sem
 *  densidade; contagem sem `grams_per_unit` fica fora (0) — como o servidor. */
export function itemGrams(item: FormulaItem): number {
  const quantity = Number(item.quantity) || 0;
  switch (item.unit) {
    case "kg":
      return quantity * 1000;
    case "L":
      return quantity * 1000 * (item.density_g_per_ml ?? 1);
    case "ml":
      return quantity * (item.density_g_per_ml ?? 1);
    case "un":
      return item.grams_per_unit ? quantity * item.grams_per_unit : 0;
    default:
      return quantity;
  }
}

export function anchorTotalOf(formula: Formula): number {
  const kind = formula.anchor.kind;
  if (kind === "flour") {
    return formula.items.filter((item) => item.role === "flour").reduce((sum, item) => sum + itemGrams(item), 0);
  }
  if (kind === "ingredient") {
    const sku = formula.anchor.sku ?? "";
    return formula.items.filter((item) => item.sku && item.sku === sku).reduce((sum, item) => sum + itemGrams(item), 0);
  }
  return formula.items.reduce((sum, item) => sum + itemGrams(item), 0);
}

export function totalMassOf(formula: Formula): number {
  return formula.items.reduce((sum, item) => sum + itemGrams(item), 0);
}

/** Percentual de um item sobre a âncora, já formatado ("70,0"); "" sem âncora. */
export function pctOf(item: FormulaItem, anchorTotal: number): string {
  if (!anchorTotal || anchorTotal <= 0) return "";
  const grams = itemGrams(item);
  if (!grams) return "";
  return formatNumber((grams / anchorTotal) * 100, 1);
}

/** Número em pt-BR (vírgula decimal, sem milhar) — só para o feedback local. */
export function formatNumber(value: number, decimals = 0): string {
  if (!Number.isFinite(value)) return "";
  return value.toFixed(decimals).replace(".", ",");
}

/** Gramas formatados para o antes/depois da padronização. */
export function gramsLabel(value: number): string {
  return `${formatNumber(Math.round(value))} g`;
}

// ── Rascunho da captura → fórmula editável ──────────────────────────────────

function asNumber(value: unknown): number {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  if (typeof value === "string") {
    const parsed = Number(value.replace(",", "."));
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

const UNITS = new Set<string>(["g", "kg", "ml", "L", "un"]);
const ROLES = new Set<string>(ROLE_OPTIONS.map((entry) => entry.value));
const ANCHORS = new Set<string>(["flour", "total", "ingredient"]);

function asUnit(value: unknown): FormulaUnit {
  if (typeof value !== "string") return "g";
  if (value === "l") return "L";
  return UNITS.has(value) ? (value as FormulaUnit) : "g";
}

function asRole(value: unknown): IngredientRole {
  return typeof value === "string" && ROLES.has(value) ? (value as IngredientRole) : "other";
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

/** Um item de captura (com o `sku` que o operador escolheu entre os candidatos)
 *  vira uma linha da fórmula. */
export function itemFromCapture(item: CaptureItemProjection): FormulaItem {
  return {
    sku: item.sku ?? "",
    name: item.name,
    role: asRole(item.role),
    quantity: asNumber(item.quantity),
    unit: asUnit(item.unit),
    note: item.original_text && item.original_text !== item.name ? item.original_text : "",
  };
}

/** O rascunho lido (anotação/foto) vira a fórmula editável: os itens vêm da
 *  lista casada (com o `sku` escolhido), a âncora e as partes do `formula` que o
 *  servidor montou quando existirem, senão sugeridas pelo conteúdo. */
export function formulaFromDraft(draft: RecipeCaptureDraftProjection): Formula {
  const items = (draft.items ?? []).map(itemFromCapture);
  const served = asRecord(draft.formula);
  const servedAnchor = asRecord(served?.anchor);
  const anchorKind =
    servedAnchor && typeof servedAnchor.kind === "string" && ANCHORS.has(servedAnchor.kind)
      ? (servedAnchor.kind as AnchorKind)
      : items.some((item) => item.role === "flour")
        ? "flour"
        : "total";
  const anchorSku = typeof servedAnchor?.sku === "string" ? servedAnchor.sku : "";
  const parts = Array.isArray(served?.parts) ? (served.parts as FormulaPart[]) : [];
  const basis = served?.basis_g;
  return {
    anchor: anchorKind === "ingredient" ? { kind: "ingredient", sku: anchorSku } : { kind: anchorKind },
    basis_g: typeof basis === "number" ? basis : null,
    standardized: served?.standardized === true,
    items,
    parts,
  };
}

/** O `formula: dict` de uma versão servida vira `Formula` editável (nova versão
 *  copia a atual). Sem inventar: campos desconhecidos ficam como vieram. */
export function formulaFromServed(served: Record<string, unknown>): Formula {
  const anchor = asRecord(served.anchor);
  const anchorKind =
    anchor && typeof anchor.kind === "string" && ANCHORS.has(anchor.kind) ? (anchor.kind as AnchorKind) : "flour";
  const anchorSku = typeof anchor?.sku === "string" ? anchor.sku : "";
  const items = Array.isArray(served.items)
    ? (served.items as Record<string, unknown>[]).map((raw) => ({
        ...raw,
        sku: typeof raw.sku === "string" ? raw.sku : "",
        name: typeof raw.name === "string" ? raw.name : "",
        role: asRole(raw.role),
        quantity: asNumber(raw.quantity),
        unit: asUnit(raw.unit),
        note: typeof raw.note === "string" ? raw.note : "",
      }))
    : [];
  return {
    anchor: anchorKind === "ingredient" ? { kind: "ingredient", sku: anchorSku } : { kind: anchorKind },
    basis_g: typeof served.basis_g === "number" ? served.basis_g : null,
    standardized: served.standardized === true,
    items,
    parts: Array.isArray(served.parts) ? (served.parts as FormulaPart[]) : [],
  };
}

/** A receita COMO FOI INFORMADA (`origin`, imutável) em linhas legíveis — a
 *  referência histórica ao lado do editor. O schema é livre (§2: quantidades,
 *  unidades, texto); só o que se reconhece vira linha, e nunca se inventa. */
export function originLines(origin: Record<string, unknown> | null | undefined): string[] {
  const record = asRecord(origin);
  if (!record) return [];
  const lines: string[] = [];
  const yieldQuantity = record.yield_quantity;
  const yieldUnit = typeof record.yield_unit === "string" ? record.yield_unit : "";
  if ((typeof yieldQuantity === "string" && yieldQuantity) || typeof yieldQuantity === "number") {
    lines.push(`Rendimento ${yieldQuantity}${yieldUnit ? ` ${yieldUnit}` : ""}`);
  }
  if (Array.isArray(record.items)) {
    for (const raw of record.items) {
      const item = asRecord(raw);
      if (!item) continue;
      const name = typeof item.name === "string" ? item.name : "";
      const quantity = item.quantity;
      const unit = typeof item.unit === "string" ? item.unit : "";
      const amount =
        (typeof quantity === "string" && quantity) || typeof quantity === "number" ? `${quantity}${unit ? ` ${unit}` : ""}` : "";
      const text = [name, amount].filter(Boolean).join(" — ");
      if (text) lines.push(text);
    }
  }
  if (typeof record.text === "string" && record.text.trim() && !lines.length) {
    lines.push(...record.text.split("\n").map((line) => line.trim()).filter(Boolean));
  }
  return lines;
}

/** Passos em textarea: uma linha por passo (vazias fora). */
export function stepsFromText(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function stepsToText(steps: readonly string[]): string {
  return steps.join("\n");
}

/** Itens da lente ainda sem insumo casado — publicar exige todo `sku` (§3). */
export function unmatchedItems(items: readonly FormulaItemProjection[]): FormulaItemProjection[] {
  return items.filter((item) => !item.matched || !item.sku);
}

// ── Erro no dialeto canônico (`{detail, field, errors}`) ────────────────────

/** O `field` apontado pelo servidor, ou "" — para a tela acender o campo certo. */
export function errorField(data: unknown): string {
  const field = asRecord(data)?.field;
  return typeof field === "string" ? field : "";
}

// ── Inventário: filtros ─────────────────────────────────────────────────────

export function filterEntries(
  entries: readonly RecipeEntryCardProjection[],
  term: string,
  kind: string,
  onlyWithoutSku: boolean,
  onlyWithDraft: boolean,
): RecipeEntryCardProjection[] {
  const needle = term.trim().toLowerCase();
  return entries.filter((entry) => {
    if (kind && entry.kind !== kind) return false;
    if (onlyWithoutSku && entry.output_sku) return false;
    if (onlyWithDraft && entry.draft_count <= 0) return false;
    if (!needle) return true;
    return (
      entry.name.toLowerCase().includes(needle) ||
      entry.ref.toLowerCase().includes(needle) ||
      entry.output_sku.toLowerCase().includes(needle) ||
      entry.output_name.toLowerCase().includes(needle)
    );
  });
}

/** Query da lista — omite filtros vazios (URLs limpas). */
export function bookQuery(term: string, kind: string, archived: boolean): Record<string, string> {
  const query: Record<string, string> = {};
  const q = term.trim();
  if (q) query.q = q;
  if (kind) query.kind = kind;
  if (archived) query.archived = "1";
  return query;
}

// ── Comparação ──────────────────────────────────────────────────────────────

export function compareQuery(aRef: string, aNumber: number, bRef: string, bNumber: number): { a: string; b: string } {
  return { a: versionRefLabel(aRef, aNumber), b: versionRefLabel(bRef, bNumber) };
}

export function comparePath(aRef: string, aNumber: number, bRef = "", bNumber = 0): string {
  const params = new URLSearchParams({ a: versionRefLabel(aRef, aNumber) });
  if (bRef && bNumber > 0) params.set("b", versionRefLabel(bRef, bNumber));
  return `/recipes/compare?${params.toString()}`;
}

// ── Foto: tamanho-alvo (a parte do canvas fica no composable) ───────────────

export const MAX_IMAGE_EDGE = 1600;

/** Dimensões-alvo para o maior lado caber em `maxEdge`; nunca amplia. */
export function downscaleTarget(
  width: number,
  height: number,
  maxEdge = MAX_IMAGE_EDGE,
): { width: number; height: number; scale: number } {
  const w = Math.max(0, Math.floor(width));
  const h = Math.max(0, Math.floor(height));
  const longest = Math.max(w, h);
  if (!longest || longest <= maxEdge) return { width: w, height: h, scale: 1 };
  const scale = maxEdge / longest;
  return {
    width: Math.max(1, Math.round(w * scale)),
    height: Math.max(1, Math.round(h * scale)),
    scale,
  };
}

/** `data:image/jpeg;base64,AAAA` → `{ media_type, data_base64 }`. */
export function splitDataUrl(dataUrl: string): { media_type: string; data_base64: string } | null {
  const match = /^data:([^;,]+);base64,(.+)$/s.exec(dataUrl);
  if (!match) return null;
  return { media_type: match[1] as string, data_base64: match[2] as string };
}

/** Tipo de saída do canvas: PNG só quando a entrada era PNG (transparência);
 *  todo o resto vira JPEG, que é o que a foto de uma ficha é. */
export function outputMediaType(inputType: string): "image/png" | "image/jpeg" {
  return inputType === "image/png" ? "image/png" : "image/jpeg";
}
