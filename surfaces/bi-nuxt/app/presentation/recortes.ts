// Os recortes de uma leitura do B.I. no formato do painel de filtros da suíte
// (`ActiveFilters`, o mesmo que o favorito guarda em `SavedView.query.filters`).
// Cada tela guarda os recortes como escolhas de um valor só ("all" quando não recorta:
// o "Todos" das abas); aqui eles viram listas e voltam. Sem Vue; testado em
// `tests/recortes.test.ts`.
import type { ActiveFilters } from "../../../operator-kit/app/types/filters";

/** Escolha de um valor por recorte: `"all"` (ou vazio) é sem recorte. */
export type RecortePicks = Record<string, string>;

export const ALL = "all";

/** `{verdict: "over", collection: "all"}` vira `{verdict: ["over"]}`. */
export function picksToFilters(picks: RecortePicks): ActiveFilters {
  const out: ActiveFilters = {};
  for (const [key, value] of Object.entries(picks)) {
    if (value && value !== ALL) out[key] = [value];
  }
  return out;
}

/**
 * O caminho de volta, só com as chaves que a tela conhece: a que falta (ou vem vazia)
 * volta a "Todos". Recorte de um valor só: de uma lista, vale o primeiro.
 */
export function filtersToPicks(filters: ActiveFilters, keys: readonly string[]): RecortePicks {
  return Object.fromEntries(keys.map((key) => [key, filters[key]?.[0] || ALL]));
}
