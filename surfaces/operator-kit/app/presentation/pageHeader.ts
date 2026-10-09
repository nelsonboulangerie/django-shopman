// A barra do topo e a toolbar no celular: a regra única do kit (dono, 08/10/2026).
//
// Barra do topo (abaixo de `sm`): ☰, o título (quebra, nunca corta) e no máximo
// `PHONE_HEADER_ICON_SLOTS` ícones fixos; todo o resto vai para UM ⋯ "Mais ações", na
// ordem declarada pela tela. Avisos é do kit e, onde aparece (sem a barra lateral na
// tela), ocupa uma das duas vagas; a outra é disputada pela Busca (prioridade
// `SEARCH_PRIORITY`) e pelas ações da tela que declaram `priority` (menor = mais
// importante). Quem perde a vaga vai para o ⋯; a Busca que perde vira "Buscar" no ⋯.
//
// Toolbar (abaixo de `sm`): uma linha só, de altura fixa: até
// `PHONE_FILTER_PRIMARY_MAX` controles primários declarados pela tela
// (`#filters-primary`) e o botão "Filtros" com o número de recortes ativos; o resto
// (`#filters`) mora no painel de baixo. Os recortes ativos aparecem como chips
// removíveis numa faixa abaixo, só quando há algum.
//
// Funções puras: o componente (`OperatorPageHeader`) só desenha o que elas decidem, e
// os testes travam a regra sem montar nada.

/** Uma ação da tela na barra do topo. Mesmo formato de um item de `NuxtDropdownMenu`. */
export interface OperatorHeaderAction {
  label: string;
  icon: string;
  /**
   * Candidata a ícone fixo no celular (menor = mais importante). Sem `priority`, a ação
   * mora no ⋯ no celular.
   */
  priority?: number;
  to?: string;
  target?: string;
  disabled?: boolean;
  color?: "primary" | "neutral" | "error";
  onSelect?: (event?: Event) => void;
}

/** Recorte ativo, desenhado como chip removível abaixo da linha da toolbar. */
export interface OperatorActiveFilter {
  key: string;
  label: string;
  remove: () => void;
}

/** Ícones fixos na barra do topo do celular, contando Avisos. */
export const PHONE_HEADER_ICON_SLOTS = 2;
/** Prioridade da Busca na disputa pela vaga (a tela vence com um número menor). */
export const SEARCH_PRIORITY = 10;
/** Controles primários que ficam na linha da toolbar do celular. */
export const PHONE_FILTER_PRIMARY_MAX = 2;

export interface PhoneHeaderLayout {
  /** A lupa fica na barra. */
  searchIcon: boolean;
  /** Ações da tela que ganharam vaga de ícone. */
  icons: OperatorHeaderAction[];
  /** O ⋯ "Mais ações": a Busca que perdeu a vaga (primeiro) e as ações, na ordem declarada. */
  overflow: Array<OperatorHeaderAction & { search?: true }>;
}

export const SEARCH_ACTION: OperatorHeaderAction & { search: true } = {
  label: "Buscar",
  icon: "i-lucide-search",
  search: true,
};

export function phoneHeaderLayout(options: {
  search: boolean;
  inbox: boolean;
  actions: readonly OperatorHeaderAction[];
}): PhoneHeaderLayout {
  const free = Math.max(0, PHONE_HEADER_ICON_SLOTS - (options.inbox ? 1 : 0));
  type Candidate = { priority: number; order: number; action?: OperatorHeaderAction };
  const candidates: Candidate[] = [];
  if (options.search) candidates.push({ priority: SEARCH_PRIORITY, order: -1 });
  options.actions.forEach((action, order) => {
    if (typeof action.priority === "number") candidates.push({ priority: action.priority, order, action });
  });
  candidates.sort((a, b) => a.priority - b.priority || a.order - b.order);
  const winners = candidates.slice(0, free);
  const searchIcon = winners.some((candidate) => !candidate.action);
  const iconSet = new Set(winners.map((candidate) => candidate.action).filter(Boolean));
  const icons = options.actions.filter((action) => iconSet.has(action));
  const overflow: PhoneHeaderLayout["overflow"] = [
    ...(options.search && !searchIcon ? [SEARCH_ACTION] : []),
    ...options.actions.filter((action) => !iconSet.has(action)),
  ];
  return { searchIcon, icons, overflow };
}

/** Quantos controles a barra do topo do celular mostra à direita do título. */
export function phoneHeaderControlCount(layout: PhoneHeaderLayout, inbox: boolean): number {
  return (layout.searchIcon ? 1 : 0) + layout.icons.length + (layout.overflow.length ? 1 : 0) + (inbox ? 1 : 0);
}

/** O rótulo do botão "Filtros" com o número de recortes ativos (nome acessível). */
export function filtersButtonLabel(active: number): string {
  if (!active) return "Filtros";
  return active === 1 ? "Filtros: 1 recorte ativo" : `Filtros: ${active} recortes ativos`;
}
