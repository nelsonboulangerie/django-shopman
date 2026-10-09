// A tabela da suíte (WP-FASE2-UX-OPERADOR, K1): as decisões puras da `OperatorTable`.
//
// Decisões do dono (09/10/2026):
//   - COMPACTA é o padrão; Confortável é a alternância, guardada por dispositivo;
//   - a linha aberta NÃO compacta: o conteúdo expandido ganha o respiro da confortável;
//   - densidade e colunas moram num botão só, "Exibir", que muda a FORMA da tabela e
//     por isso nunca entra no painel de filtros.
//
// A escolha do dispositivo vai num cookie (não `localStorage`): a tabela é desenhada no
// servidor, então ele precisa saber a densidade e as colunas para a tela não nascer de
// um jeito e piscar para outro ao hidratar. Guardamos as colunas OCULTAS: coluna nova
// que o servidor passe a mandar (um canal recém-criado) nasce visível.

import type { RowData } from "@tanstack/table-core";

// O `meta` da coluna da suíte, para o TypeScript das telas (o Nuxt UI já soma `class`
// e `style`).
declare module "@tanstack/table-core" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    /** O nome da coluna no "Exibir" quando o `header` não é texto. */
    label?: string;
    /** Coluna de apoio: some no celular (por CSS). */
    supporting?: boolean;
  }
}

export type OperatorTableDensity = "compact" | "comfortable";

export const OPERATOR_TABLE_DEFAULT_DENSITY: OperatorTableDensity = "compact";

export interface OperatorTableViewState {
  density: OperatorTableDensity;
  /** Colunas ocultas, por id. */
  hidden: string[];
}

export const OPERATOR_TABLE_VIEW_COOKIE_PREFIX = "op-table-";

/** O nome do cookie da tabela: só letras, números e hífen. */
export function operatorTableViewCookie(key: string): string {
  return `${OPERATOR_TABLE_VIEW_COOKIE_PREFIX}${key.replace(/[^a-zA-Z0-9-]/g, "-")}`;
}

export function defaultTableView(): OperatorTableViewState {
  return { density: OPERATOR_TABLE_DEFAULT_DENSITY, hidden: [] };
}

/**
 * O que veio do cookie, higienizado: valor estranho (cookie editado, formato antigo)
 * volta ao padrão em vez de quebrar a tela.
 */
export function parseTableView(raw: unknown): OperatorTableViewState {
  if (!raw || typeof raw !== "object") return defaultTableView();
  const value = raw as Partial<Record<keyof OperatorTableViewState, unknown>>;
  const density: OperatorTableDensity =
    value.density === "comfortable" ? "comfortable" : OPERATOR_TABLE_DEFAULT_DENSITY;
  const hidden = Array.isArray(value.hidden)
    ? [...new Set(value.hidden.filter((id): id is string => typeof id === "string" && id.length > 0))]
    : [];
  return { density, hidden };
}

/** Ocultas → o `column-visibility` do TanStack (ausente = visível). */
export function visibilityFromHidden(hidden: readonly string[]): Record<string, boolean> {
  return Object.fromEntries(hidden.map((id) => [id, false]));
}

export function toggleHidden(hidden: readonly string[], id: string, visible: boolean): string[] {
  const rest = hidden.filter((item) => item !== id);
  return visible ? rest : [...rest, id];
}

/**
 * O espaçamento de cada densidade. É o único `:ui` da tabela na suíte: mora aqui e no
 * componente, nunca na tela. A célula QUEBRA (`whitespace-normal`): texto da casa nunca
 * é cortado; número e ação que não devem quebrar dizem isso na própria célula.
 */
export function tableDensityUi(density: OperatorTableDensity) {
  return density === "compact"
    ? { th: "px-2 py-1 text-sm", td: "px-2 py-1.5 text-sm whitespace-normal" }
    : { th: "px-4 py-3.5 text-sm", td: "p-4 text-sm whitespace-normal" };
}

/**
 * O respiro extra do conteúdo aberto: na compacta, somado ao `px-2 py-1.5` da célula,
 * dá o `px-4 py-3` da confortável. Na confortável a célula já respira.
 */
export function expandedPadding(density: OperatorTableDensity): string {
  return density === "compact" ? "px-2 py-1.5" : "";
}

/**
 * A largura das colunas de controle (caixa de marcar, seta de abrir), com o padding da
 * densidade: a caixa tem 16 px e a seta é um botão `md` de 32 px.
 */
export function leadWidth(id: "select" | "expand" | string, density: OperatorTableDensity): number {
  const pad = density === "compact" ? 16 : 32;
  return (id === "expand" ? 32 : 16) + pad;
}

export type SortState = false | "asc" | "desc";

export function sortIcon(state: SortState): string {
  return state === "asc"
    ? "i-lucide-arrow-up"
    : state === "desc"
      ? "i-lucide-arrow-down"
      : "i-lucide-arrow-up-down";
}

/** O nome acessível do cabeçalho que ordena: diz o estado e o que o toque faz. */
export function sortLabel(name: string, state: SortState): string {
  if (state === "asc") return `${name}, em ordem crescente. Tocar inverte`;
  if (state === "desc") return `${name}, em ordem decrescente. Tocar inverte`;
  return `Ordenar por ${name.toLowerCase()}`;
}

/** A classe que some com a coluna de apoio no celular (CSS, nunca media query em JS). */
export const SUPPORTING_COLUMN_CLASS = "max-sm:hidden";

/** A coluna fixada cabe no celular: largura máxima, e o texto dela quebra. */
export const PINNED_COLUMN_CLASS = "max-sm:max-w-40";

type CellClass<A> = string | ((arg: A) => string) | undefined;

/** Junta uma classe a `meta.class.th`/`td`, seja ela texto ou função. */
export function appendClass<A>(current: CellClass<A>, extra: string): string | ((arg: A) => string) {
  if (!extra) return current ?? "";
  if (typeof current === "function") return (arg: A) => `${current(arg)} ${extra}`.trim();
  return `${current ?? ""} ${extra}`.trim();
}

export interface OperatorTableColumnMeta {
  /** O nome da coluna no "Exibir" quando o `header` não é texto. */
  label?: string;
  /** Coluna de apoio: some no celular (por CSS). */
  supporting?: boolean;
}

interface ColumnLike {
  id?: string;
  accessorKey?: string | number | symbol;
  header?: unknown;
  enableHiding?: boolean;
  meta?: { label?: string };
}

/** O id que o TanStack dá à coluna: `id` ou `accessorKey`. */
export function columnId(column: ColumnLike): string {
  return String(column.id ?? column.accessorKey ?? "");
}

/** O nome da coluna para o "Exibir" e para o cabeçalho que ordena. */
export function columnLabel(column: ColumnLike): string {
  if (column.meta?.label) return column.meta.label;
  if (typeof column.header === "string" && column.header) return column.header;
  return columnId(column);
}

/** As colunas que a pessoa pode esconder: as que não dizem `enableHiding: false`. */
export function hideableColumns(columns: readonly ColumnLike[]): { id: string; label: string }[] {
  return columns
    .filter((column) => column.enableHiding !== false && columnId(column))
    .map((column) => ({ id: columnId(column), label: columnLabel(column) }));
}

/** Ocultas higienizadas contra as colunas de agora (id que sumiu do servidor sai). */
export function reconcileHidden(hidden: readonly string[], known: readonly string[]): string[] {
  const set = new Set(known);
  return hidden.filter((id) => set.has(id));
}
