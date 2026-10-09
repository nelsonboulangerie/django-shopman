// FilterBar — transformações puras do estado de filtros. O componente só renderiza
// o que sai daqui, então a lógica de "o que está ativo", "como se lê o chip" e "o
// que acontece ao clicar numa opção" é testável sem montar Vue.
import { LIST_TYPES, RANGE_TYPES, type ActiveFilters, type FilterDimension, type FilterOption } from "../types/filters";

// Boolean é a única dimensão cujas opções não vêm do app: é sempre sim/não. Ter o
// par aqui evita que cada superfície reinvente o rótulo.
export const BOOLEAN_OPTIONS: FilterOption[] = [
  { value: "true", label: "Sim" },
  { value: "false", label: "Não" },
];

export function optionsFor(dimension: FilterDimension): FilterOption[] {
  return dimension.type === "boolean" ? BOOLEAN_OPTIONS : (dimension.options ?? []);
}

export function isListType(dimension: FilterDimension): boolean {
  return LIST_TYPES.includes(dimension.type);
}

export function isRangeType(dimension: FilterDimension): boolean {
  return RANGE_TYPES.includes(dimension.type);
}

// A partir de quantas opções a lista ganha busca sozinha: até aqui, ler é mais
// rápido que digitar.
export const SEARCH_THRESHOLD = 8;

export function needsSearch(dimension: FilterDimension): boolean {
  return dimension.searchable ?? optionsFor(dimension).length >= SEARCH_THRESHOLD;
}

// Busca sem acento e sem caixa: "cartao" acha "Cartão".
function fold(text: string): string {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLocaleLowerCase("pt-BR").trim();
}

/** Opções que casam a busca, na ordem declarada. Busca vazia devolve todas. */
export function searchOptions(options: FilterOption[], term: string): FilterOption[] {
  const needle = fold(term);
  if (!needle) return options;
  return options.filter((option) => fold(option.label).includes(needle) || fold(option.value).includes(needle));
}

// Uma dimensão só conta como ativa quando tem valor útil: lista vazia (ou um
// intervalo com os dois lados abertos) é o mesmo que não filtrar, e não vira chip.
export function isActive(filters: ActiveFilters, id: string): boolean {
  return (filters[id] ?? []).some((value) => value !== "");
}

export function isSelected(filters: ActiveFilters, dimension: FilterDimension, value: string): boolean {
  return (filters[dimension.id] ?? []).includes(value);
}

function dayMonth(iso: string): string {
  const [, month, day] = iso.split("-");
  return day && month ? `${day}/${month}` : iso;
}

/** O valor de um intervalo como se lê: "10 a 50", "a partir de 10", "até 50". */
export function rangeText(dimension: FilterDimension, [from = "", to = ""]: string[]): string {
  const show = (value: string) =>
    dimension.type === "date-range" ? dayMonth(value) : (dimension.formatValue?.(value) ?? value);
  if (from && to) return from === to ? show(from) : `${show(from)} a ${show(to)}`;
  if (from) return `a partir de ${show(from)}`;
  if (to) return `até ${show(to)}`;
  return "";
}

/**
 * Rótulo do chip: "Estoque: baixo, esgotado" (multi) · "Publicado: sim" (boolean) ·
 * "Cliente: maria" (texto) · "Total: R$ 10,00 a R$ 50,00" (intervalo).
 */
export function chipLabel(dimension: FilterDimension, filters: ActiveFilters): string {
  const values = filters[dimension.id] ?? [];
  if (isRangeType(dimension)) return `${dimension.label}: ${rangeText(dimension, values)}`;
  if (dimension.type === "text") return `${dimension.label}: ${values[0] ?? ""}`;
  const options = optionsFor(dimension);
  const labelOf = (value: string) => options.find((o) => o.value === value)?.label ?? value;
  return `${dimension.label}: ${values.map(labelOf).join(", ")}`;
}

/** Dimensões com recorte ativo, na ordem em que o app as declarou (chips estáveis). */
export function activeDimensions(dimensions: FilterDimension[], filters: ActiveFilters): FilterDimension[] {
  return dimensions.filter((d) => isActive(filters, d.id));
}

/**
 * Clique numa opção → próximo estado. Multi-select acumula/remove; single-select e
 * boolean trocam o valor (lista de um elemento só), e reclicar o valor já escolhido
 * LIMPA a dimensão (o mesmo gesto que ligou desliga — não há botão "todos").
 */
export function toggleOption(
  filters: ActiveFilters,
  dimension: FilterDimension,
  value: string,
): ActiveFilters {
  const next = { ...filters };
  if (dimension.type === "multi-select") {
    const current = next[dimension.id] ?? [];
    const picked = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
    if (picked.length) next[dimension.id] = picked;
    else delete next[dimension.id];
    return next;
  }
  if (isSelected(filters, dimension, value)) delete next[dimension.id];
  else next[dimension.id] = [value];
  return next;
}

export function clearDimension(filters: ActiveFilters, id: string): ActiveFilters {
  const next = { ...filters };
  delete next[id];
  return next;
}

/**
 * Grava o valor de um campo (texto ou intervalo). Valor sem nada útil apaga a
 * dimensão: o chip some e a URL fica limpa.
 */
export function setValues(filters: ActiveFilters, id: string, values: string[]): ActiveFilters {
  const next = { ...filters };
  const cleaned = values.map((value) => value.trim());
  if (cleaned.some((value) => value !== "")) next[id] = cleaned;
  else delete next[id];
  return next;
}

/**
 * Os campos aplicados como recortes ativos do cabeçalho (`active-filters` do
 * `OperatorPageHeader`): o mesmo rótulo do chip da barra, e o × que tira o campo.
 * `update` recebe o próximo estado (o `v-model` da tela).
 */
export function filterBarActiveFilters(
  dimensions: FilterDimension[],
  filters: ActiveFilters,
  update: (next: ActiveFilters) => void,
): { key: string; label: string; remove: () => void }[] {
  return activeDimensions(dimensions, filters).map((dimension) => ({
    key: dimension.id,
    label: chipLabel(dimension, filters),
    remove: () => update(clearDimension(filters, dimension.id)),
  }));
}

// ── URL ──────────────────────────────────────────────────────────────
//
// Uma chave por dimensão, com o id dela: `?payment=pix,card&total=1000..5000`.
// Lista → valores separados por vírgula (valor de opção não leva vírgula); texto →
// o texto cru; intervalo → `de..até`, lado aberto vazio (`..5000`, `2026-10-01..`).
// A URL é a fonte: recarregar, voltar do detalhe e mandar o link devolvem o mesmo
// recorte.

type RouteQueryValue = string | null | (string | null)[] | undefined;

function firstValue(value: RouteQueryValue): string {
  return String((Array.isArray(value) ? value[0] : value) ?? "");
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

function validRangeSide(dimension: FilterDimension, value: string): string {
  if (!value) return "";
  if (dimension.type === "date-range") return ISO_DAY.test(value) ? value : "";
  return Number.isFinite(Number(value)) ? value : "";
}

/** Recorte → querystring (só as dimensões ativas). */
export function filtersToQuery(dimensions: FilterDimension[], filters: ActiveFilters): Record<string, string> {
  const out: Record<string, string> = {};
  for (const dimension of activeDimensions(dimensions, filters)) {
    const values = filters[dimension.id] ?? [];
    if (isRangeType(dimension)) out[dimension.id] = `${values[0] ?? ""}..${values[1] ?? ""}`;
    else if (dimension.type === "text") out[dimension.id] = values[0] ?? "";
    else out[dimension.id] = values.join(",");
  }
  return out;
}

/**
 * Querystring → recorte. Lê só as chaves das dimensões declaradas; valor malformado
 * (data que não é data, número que não é número, boolean fora de sim/não) é
 * descartado em vez de virar filtro que não casa nada. Opção de lista NÃO é
 * conferida contra `options`: elas podem chegar depois, do servidor.
 */
export function filtersFromQuery(
  dimensions: FilterDimension[],
  query: Record<string, RouteQueryValue>,
): ActiveFilters {
  const out: ActiveFilters = {};
  for (const dimension of dimensions) {
    const raw = firstValue(query[dimension.id]).trim();
    if (!raw) continue;
    let values: string[];
    if (isRangeType(dimension)) {
      const [from = "", to = ""] = raw.split("..");
      values = [validRangeSide(dimension, from.trim()), validRangeSide(dimension, to.trim())];
    } else if (dimension.type === "text") {
      values = [raw];
    } else {
      values = [...new Set(raw.split(",").map((v) => v.trim()).filter(Boolean))];
      if (dimension.type === "boolean") values = values.filter((v) => v === "true" || v === "false").slice(0, 1);
      if (dimension.type === "single-select") values = values.slice(0, 1);
    }
    if (values.some((value) => value !== "")) out[dimension.id] = values;
  }
  return out;
}

/**
 * A query nova da rota: troca as chaves das dimensões e preserva o resto (período,
 * busca, aba). `resetKeys` some quando o recorte muda (a página 3 de um recorte não
 * existe no outro).
 */
export function mergeFilterQuery(
  current: Record<string, RouteQueryValue>,
  dimensions: FilterDimension[],
  filters: ActiveFilters,
  resetKeys: readonly string[] = [],
): Record<string, RouteQueryValue> {
  const next: Record<string, RouteQueryValue> = { ...current };
  for (const dimension of dimensions) delete next[dimension.id];
  for (const key of resetKeys) delete next[key];
  return { ...next, ...filtersToQuery(dimensions, filters) };
}
