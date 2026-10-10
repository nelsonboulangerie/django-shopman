// Presentation — relatórios e gestão de produção (página /reports, persona
// GESTOR). Transforms puras sobre as projections servidas por
// shopman/backstage/projections/production.py via a API de relatórios; as
// linhas já chegam prontas de tela (qty_*, yield_rate, duration pré-formatados)
// — esta camada só deriva rótulos, a query dos filtros e o link do CSV.

import type { ActiveFilters, FilterDimension } from "../../../operator-kit/app/types/filters";

export type ReportKind =
  "history" | "operator_productivity" | "recipe_waste" | "quality";
export type ReportSort =
  | "default"
  | "date_asc"
  | "date_desc"
  | "name_asc"
  | "name_desc"
  | "quantity_asc"
  | "quantity_desc";

export const REPORT_KINDS: readonly { kind: ReportKind; label: string }[] = [
  { kind: "history", label: "Histórico" },
  { kind: "operator_productivity", label: "Produtividade" },
  { kind: "recipe_waste", label: "Desperdício" },
  // A partição do QC agregada por receita × grau × defeito (ADR-017 §8):
  // é este relatório que diz se o forno 2 está queimando.
  { kind: "quality", label: "Qualidade" },
] as const;

export function reportKindLabel(kind: ReportKind): string {
  return (
    REPORT_KINDS.find((entry) => entry.kind === kind)?.label ?? "Histórico"
  );
}

/** Filtros da página de relatórios — espelham os query params da API. */
export interface ReportFiltersQuery {
  selected_only: true;
  report_kind: ReportKind;
  date_from: string;
  date_to: string;
  recipe_ref: string;
  position_ref: string;
  operator_ref: string;
  sort: ReportSort;
  page_size: number;
  cursor: string;
}

/** Query object da API de relatórios — omite filtros vazios (URLs limpas). */
export function reportsQuery(
  filters: ReportFiltersQuery,
): Record<string, string | number | boolean> {
  const query: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(filters)) {
    if (value) query[key] = value;
  }
  return query;
}

/** Link direto do download CSV (mesmo endpoint, `format=csv`). O clique é um
 *  `<a href>` comum: o navegador baixa via BFF com a sessão do operador. */
export function reportsCsvUrl(filters: ReportFiltersQuery): string {
  const query = reportsQuery(filters);
  delete query.cursor;
  delete query.page_size;
  const params = new URLSearchParams(
    Object.entries({ ...query, format: "csv" }).map(([key, value]) => [
      key,
      String(value),
    ]),
  );
  return `/api/v1/backstage/production/reports/?${params.toString()}`;
}

export function reportDateError(dateFrom: string, dateTo: string): string {
  if (!dateFrom || !dateTo) return "Informe as duas datas do período.";
  const start = Date.parse(`${dateFrom}T00:00:00Z`);
  const end = Date.parse(`${dateTo}T00:00:00Z`);
  if (!Number.isFinite(start) || !Number.isFinite(end))
    return "Informe datas válidas.";
  if (start > end) return "A data final não pode ser anterior à data inicial.";
  const days = Math.floor((end - start) / 86_400_000) + 1;
  return days > 93 ? "O período máximo para relatórios é de 93 dias." : "";
}

/** Capacidade do dia em rótulo calmo: null = sem capacidade configurada. */
export function capacityLabel(capacityPercent: number | null): string {
  if (capacityPercent === null || capacityPercent === undefined) return "";
  return `${capacityPercent}%`;
}

// ── O painel de filtros (fase 2, `OperatorFilterPanel`) ─────────────────────
// Ficha técnica, posto e operador são os recortes do painel; o período mora na Data
// dele. A ordenação não é recorte: fica ao lado, no seletor dela.

/** Os períodos que o relatório oferece (a API aceita até 93 dias). */
export const REPORT_PERIOD_PRESETS = ["day", "week", "month", "7d", "28d"] as const;

type ReportRecortes = Pick<ReportFiltersQuery, "recipe_ref" | "position_ref" | "operator_ref">;

const REPORT_DIMENSION_KEYS: Record<string, keyof ReportRecortes> = {
  recipe: "recipe_ref",
  position: "position_ref",
  operator: "operator_ref",
};

/** As dimensões do painel: ficha técnica e posto (lista), operador (texto digitado). */
export function reportDimensions(
  recipes: readonly { ref: string; name: string }[],
  positions: readonly { ref: string; name: string }[],
): FilterDimension[] {
  return [
    {
      id: "recipe",
      label: "Ficha técnica",
      type: "single-select",
      options: recipes.map((recipe) => ({ value: recipe.ref, label: recipe.name })),
    },
    {
      id: "position",
      label: "Posto",
      type: "single-select",
      options: positions.map((position) => ({ value: position.ref, label: position.name })),
    },
    { id: "operator", label: "Operador", type: "text", options: [], placeholder: "Nome ou usuário" },
  ];
}

/** Os recortes do rascunho na forma do painel (vazio não é recorte). */
export function reportPanelFilters(draft: ReportRecortes): ActiveFilters {
  const out: ActiveFilters = {};
  for (const [id, key] of Object.entries(REPORT_DIMENSION_KEYS)) {
    const value = draft[key].trim();
    if (value) out[id] = [value];
  }
  return out;
}

/** O recorte do painel (ou de um favorito) de volta para o rascunho: os três de uma vez. */
export function reportRecortesFromPanel(active: ActiveFilters): ReportRecortes {
  return {
    recipe_ref: active.recipe?.[0] ?? "",
    position_ref: active.position?.[0] ?? "",
    operator_ref: active.operator?.[0] ?? "",
  };
}
