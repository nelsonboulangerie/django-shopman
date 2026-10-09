// Tipos da proposta da fase 2 (`pages/proposal/fase2`). Material de decisão: se o dono
// aprovar, cada tipo nasce na peça do kit e este arquivo morre com a página.

export interface Fase2Order {
  ref: string;
  customer: string;
  channel: string;
  stage: "Novo" | "Em preparo" | "Pronto" | "Atrasado";
  total_q: number;
  eta: string;
  items: string[];
}

export interface QuickFilter {
  value: string;
  label: string;
  count?: number;
  favorite?: boolean;
}

export interface SavedView {
  id: string;
  name: string;
  summary: string;
  pinned: boolean;
}
