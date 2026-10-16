// O painel de filtros único da suíte (`OperatorFilterPanel`, WP-FASE2-UX-OPERADOR K4).
//
// Decisões do dono (09/10/2026): UM painel, igual no celular e na mesa, na ordem do
// Odoo, com os FAVORITOS entre as primeiras opções: Favoritos → Filtros rápidos → Data
// (o período das LISTAS mora aqui) → Agrupar por → Filtros completos, e no pé "Salvar
// como favorito". O botão é só o ícone com o número no celular; ícone, "Filtros" e o
// número na mesa. Favorito é por pessoa e mora no servidor (`useSavedViews`).
//
// O recorte é o mesmo `ActiveFilters` do `FilterBar` (a URL já sabe guardá-lo), mais o
// período e o agrupamento quando a tela os tem. Funções puras: o componente só desenha.

import type { ActiveFilters, FilterDimension } from "../types/filters";
import { CUSTOM_PERIOD, findPreset, type PeriodSelection } from "./dates";
import { activeDimensions, isListType } from "./filterBar";

/** O recorte inteiro de uma tela: o que o favorito guarda. */
export interface FilterPanelQuery {
  filters: ActiveFilters;
  period?: PeriodSelection;
  group?: string;
}

/** Um filtro rápido: uma opção de uma dimensão, com um nome próprio ("Cancelados"). */
export interface FilterPanelQuick {
  dimension: string;
  value: string;
  label: string;
}

export interface FilterPanelGroupOption {
  value: string;
  label: string;
}

/** As dimensões que o painel sabe editar: as de lista e a de texto (pela busca). */
export function panelDimensions(dimensions: readonly FilterDimension[]): FilterDimension[] {
  return dimensions.filter((dimension) => isListType(dimension) || dimension.type === "text");
}

/** Dois períodos são o mesmo (ausente só iguala ausente). */
export function samePeriod(a?: PeriodSelection, b?: PeriodSelection): boolean {
  if (!a || !b) return !a && !b;
  return a.preset === b.preset && (a.from ?? "") === (b.from ?? "") && (a.to ?? "") === (b.to ?? "");
}

/** Filtros sem as dimensões vazias, com os valores em ordem: a forma comparável. */
export function normalizeFilters(filters: ActiveFilters): ActiveFilters {
  return Object.fromEntries(
    Object.entries(filters)
      .map(([key, values]) => [key, [...values].filter((value) => value !== "").sort()] as const)
      .filter(([, values]) => values.length > 0)
      .sort(([a], [b]) => a.localeCompare(b)),
  );
}

/** Dois recortes são o mesmo (para marcar o favorito ativo). */
export function sameQuery(a: FilterPanelQuery, b: FilterPanelQuery): boolean {
  return (
    JSON.stringify(normalizeFilters(a.filters)) === JSON.stringify(normalizeFilters(b.filters ?? {})) &&
    samePeriod(a.period, b.period) &&
    (a.group ?? "") === (b.group ?? "")
  );
}

/**
 * Quantos recortes estão ativos (o número do botão): cada dimensão com valor, o período
 * fora do padrão da tela e o agrupamento fora do padrão.
 */
export function activeRecortes(
  dimensions: readonly FilterDimension[],
  query: FilterPanelQuery,
  defaults: { period?: PeriodSelection; group?: string } = {},
): number {
  const filters = activeDimensions([...dimensions], query.filters).length;
  const period = query.period && defaults.period && !samePeriod(query.period, defaults.period) ? 1 : 0;
  const group = query.group && query.group !== (defaults.group ?? "") ? 1 : 0;
  return filters + period + group;
}

/** O nome acessível do botão: "Filtros", "Filtros: 1 recorte ativo", "Filtros: 3 recortes ativos". */
export function filterPanelLabel(active: number): string {
  if (!active) return "Filtros";
  return active === 1 ? "Filtros: 1 recorte ativo" : `Filtros: ${active} recortes ativos`;
}

/** O nome de um período no painel: "Dia", "Últimos 7 dias", "Personalizado". */
export function periodOptionLabel(key: string): string {
  if (key === CUSTOM_PERIOD) return "Personalizado";
  const preset = findPreset(key);
  return preset?.title ?? preset?.label ?? key;
}

/** O recorte guardado no favorito: só o que a tela tem (sem período, não há período). */
export function queryToSave(query: FilterPanelQuery): FilterPanelQuery {
  return {
    filters: normalizeFilters(query.filters),
    ...(query.period ? { period: { preset: query.period.preset, from: query.period.from ?? "", to: query.period.to ?? "" } } : {}),
    ...(query.group ? { group: query.group } : {}),
  };
}

/** Marca um filtro rápido (soma com os outros da mesma dimensão: OU). */
export function quickActive(filters: ActiveFilters, quick: FilterPanelQuick): boolean {
  return (filters[quick.dimension] ?? []).includes(quick.value);
}

/** A frase do texto digitado: `Cliente contém “ana”`. */
export function containsLabel(dimension: FilterDimension, term: string): string {
  return `${dimension.label} contém “${term}”`;
}
