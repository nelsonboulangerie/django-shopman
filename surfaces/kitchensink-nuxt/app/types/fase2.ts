// Tipos da proposta da fase 2 (`pages/proposal/fase2`). Material de decisão: se o dono
// aprovar, cada tipo nasce na peça do kit e este arquivo morre com a página.

export interface Fase2Order {
  ref: string;
  customer: string;
  channel: string;
  stage: "Novo" | "Em preparo" | "Pronto" | "Atrasado" | "Retirado" | "Entregue" | "Cancelado";
  total_q: number;
  eta: string;
  items: string[];
  payment?: string;
  date?: string;
}

export interface QuickFilter {
  value: string;
  label: string;
  count?: number;
  favorite?: boolean;
  /** Sub-seção: muda a URL em vez da query. */
  to?: string;
}

export interface SavedView {
  id: string;
  name: string;
  summary: string;
  pinned: boolean;
  /** Publicado pelo gerente para a equipe (pergunta 2, opção 2 do dono). */
  shared?: boolean;
  /** O recorte guardado (o que "aplicar" devolve à tela). */
  state?: Partial<Fase2FilterState>;
}

/** Uma dimensão do painel de filtros (Odoo: um grupo; OR dentro, AND entre grupos). */
export interface Fase2FilterDimension {
  id: string;
  label: string;
  options: { value: string; label: string; count?: number }[];
}

/** O estado inteiro de um recorte: o que o favorito guarda e a URL carrega. */
export interface Fase2FilterState {
  quick: string[];
  period: string;
  groupBy: string;
  values: Record<string, string[]>;
  text: { field: string; term: string }[];
  favorite: string;
}

export interface Fase2SearchItem {
  label: string;
  suffix?: string;
  icon: string;
}

export interface Fase2Material {
  sku: string;
  name: string;
  category: string;
  supplier: string;
  stock: string;
  min: string;
  low: boolean;
}

export interface Fase2Product {
  sku: string;
  name: string;
  price_q: number;
  stock?: string;
}
