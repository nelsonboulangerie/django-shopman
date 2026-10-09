// O recorte da proposta da fase 2 como dados puros: o painel de filtros, os chips e o
// favorito leem e escrevem o MESMO estado. No kit, isto vira a presentation do K4.
// Regra do Odoo (documentação "Search, filter, and group records"): dentro de um grupo
// as opções somam (OU); entre grupos, todas valem (E). Favorito aplicado aparece como
// UM recorte com o nome dele; mexer em qualquer parte o desfaz em recortes soltos.
import type { Fase2FilterDimension, Fase2FilterState, SavedView } from "../types/fase2";

export interface Fase2FilterConfig {
  /** "pedidos", "insumos": o substantivo do botão "Ver 7 pedidos". */
  noun: string;
  quick: { value: string; label: string }[];
  periods: { value: string; label: string }[];
  /** O período que não conta como recorte (o padrão da tela). Vazio = sem período. */
  defaultPeriod: string;
  groups: { value: string; label: string }[];
  dimensions: Fase2FilterDimension[];
  textFields: { value: string; label: string }[];
}

export interface Fase2Facet {
  id: string;
  label: string;
  favorite?: boolean;
}

export function facetsOf(state: Fase2FilterState, config: Fase2FilterConfig, views: readonly SavedView[]): Fase2Facet[] {
  if (state.favorite) {
    const view = views.find((item) => item.id === state.favorite);
    if (view) return [{ id: "favorite", label: view.name, favorite: true }];
  }
  const facets: Fase2Facet[] = [];
  for (const value of state.quick) {
    const quick = config.quick.find((item) => item.value === value);
    if (quick) facets.push({ id: `quick:${value}`, label: quick.label });
  }
  if (config.defaultPeriod && state.period !== config.defaultPeriod) {
    const period = config.periods.find((item) => item.value === state.period);
    if (period) facets.push({ id: "period", label: period.label });
  }
  for (const dimension of config.dimensions) {
    const values = state.values[dimension.id] ?? [];
    if (!values.length) continue;
    const labels = values.map((value) => dimension.options.find((option) => option.value === value)?.label ?? value);
    facets.push({ id: `dim:${dimension.id}`, label: `${dimension.label}: ${labels.join(" ou ")}` });
  }
  for (const [index, text] of state.text.entries()) {
    const field = config.textFields.find((item) => item.value === text.field)?.label ?? text.field;
    facets.push({ id: `text:${index}`, label: `${field} contém “${text.term}”` });
  }
  if (state.groupBy) {
    const group = config.groups.find((item) => item.value === state.groupBy);
    if (group) facets.push({ id: "group", label: `Agrupado por ${group.label.toLowerCase()}` });
  }
  return facets;
}

export function emptyState(defaultPeriod: string): Fase2FilterState {
  return { quick: [], period: defaultPeriod, groupBy: "", values: {}, text: [], favorite: "" };
}

export function removeFacet(state: Fase2FilterState, id: string, defaultPeriod: string): Fase2FilterState {
  if (id === "favorite") return emptyState(defaultPeriod);
  const values = { ...state.values };
  const next: Fase2FilterState = { ...state, favorite: "", values, text: [...state.text] };
  if (id.startsWith("quick:")) next.quick = state.quick.filter((value) => `quick:${value}` !== id);
  else if (id === "period") next.period = defaultPeriod;
  else if (id === "group") next.groupBy = "";
  else if (id.startsWith("dim:")) next.values = Object.fromEntries(Object.entries(values).filter(([key]) => key !== id.slice(4)));
  else if (id.startsWith("text:")) next.text.splice(Number(id.slice(5)), 1);
  return next;
}

export function applyView(view: SavedView, defaultPeriod: string): Fase2FilterState {
  return { ...emptyState(defaultPeriod), ...view.state, favorite: view.id };
}

/** Qualquer mudança no recorte desfaz o favorito aplicado (vira recortes soltos). */
export function edit(state: Fase2FilterState, change: Partial<Fase2FilterState>): Fase2FilterState {
  return { ...state, ...change, favorite: "" };
}

export function toggle(list: readonly string[], value: string): string[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

/** O resumo que o "Salvar como favorito" mostra antes de pedir o nome. */
export function summaryOf(state: Fase2FilterState, config: Fase2FilterConfig, views: readonly SavedView[]): string {
  return facetsOf({ ...state, favorite: "" }, config, views)
    .map((facet) => facet.label)
    .join(" · ");
}
