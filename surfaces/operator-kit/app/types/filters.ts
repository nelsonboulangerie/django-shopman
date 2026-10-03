// Contrato do recorte por dimensões (FilterBar) — genérico, sem domínio.
// O app hospedeiro descreve as dimensões (o QUE se pode filtrar) e guarda os
// filtros ativos; o componente só edita esse estado. Quem interpreta o valor é o
// app (a barra não sabe o que é "sync" ou "estoque").
//
// Chaves em inglês (id/value), rótulos em pt-BR (label) — convenção do projeto.

// Tipos de lista (o operador marca opções): single-select, multi-select, boolean.
// Tipos de campo (o operador digita): text (contém), number-range e date-range
// (De/Até, qualquer um dos lados pode ficar aberto).
export type FilterType = "single-select" | "multi-select" | "boolean" | "text" | "number-range" | "date-range";

export const RANGE_TYPES: readonly FilterType[] = ["number-range", "date-range"];
export const LIST_TYPES: readonly FilterType[] = ["single-select", "multi-select", "boolean"];

export interface FilterOption {
  value: string;
  label: string;
  count?: number; // quantos itens casariam esta opção (opcional; some quando indefinido)
}

export interface FilterDimension {
  /** Chave do recorte; é também a chave na querystring (`?payment=pix,card`). */
  id: string;
  label: string;
  type: FilterType;
  /** Opções dos tipos de lista. Os tipos de campo não usam: passe `[]`. */
  options: FilterOption[];
  /** Busca dentro das opções. Padrão: liga sozinha a partir de 8 opções. */
  searchable?: boolean;
  /** Dica do campo de texto / número ("Nome ou telefone"). */
  placeholder?: string;
  /** Como o chip escreve um valor de intervalo numérico (ex.: centavos → "R$ 12,00"). */
  formatValue?: (value: string) => string;
}

// Valor por dimensão: SEMPRE lista de strings, qualquer que seja o tipo. Single-select
// e boolean guardam um único elemento (boolean usa "true"/"false"), multi-select
// guarda vários, text guarda [texto] e os intervalos guardam [de, até] (lado aberto
// = ""). A forma única sobrevive à querystring sem serializar/desserializar.
// Dimensão AUSENTE (ou com lista vazia) = sem recorte — não existe "todos" como valor.
export type ActiveFilters = Record<string, string[]>;
