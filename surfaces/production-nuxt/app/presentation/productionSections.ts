// Presentation — as seções da Produção no rail da suíte (V4-PROD). Puro: quem decide
// se o operador vê Receitas ou Relatórios é o servidor (as sondas de acesso); aqui só
// se monta a lista.
//
// Desenho da prévia v4 (`plano-porque4.html`, `producao-qualidade4.html`): em cima o
// ciclo do lote, com a tecla impressa sob o nome (Alt1 a Alt5, decisão #1433:
// Planejamento · Preparação · Abertura · Fechamento · Qualidade), e logo abaixo os
// Timers da bancada, com a contagem de ativos no selo e o ponto quando um toca, e
// Ajustes (V6-KIT, R02): o que não é etapa (Receitas, Relatórios, o Letreiro) mora na
// tela de Ajustes, e o pé do rail é o da suíte. No celular a barra do polegar leva
// as quatro primeiras etapas e o "Mais" guarda o resto (`phoneSections`).
// Na barra do polegar, Planejamento e Preparação aparecem como "Plano" e "Preparo"
// (as prévias v4 do celular e da Qualidade): os cinco nomes cheios não cabem em 1/5 de
// um celular de 320px. O nome acessível continua o cheio.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

export interface ProductionSectionsInput {
  /** Timers ativos neste dispositivo (o servidor não os conhece). */
  timersActive?: number;
  /** Timers tocando agora: vira o ponto de atenção do item Timers. */
  timersRinging?: number;
  /** Lotes fechados esperando a revisão da Qualidade (só quando a tela sabe). */
  qualityPending?: number;
  canViewRecipes?: boolean;
  canViewReports?: boolean;
}

/** O ciclo do lote, na ordem do dia, com as teclas Alt+1 a Alt+5. */
export const PRODUCTION_STAGES: readonly OperatorSection[] = [
  { key: "plan", label: "Planejamento", shortLabel: "Plano", icon: "lucide:layout-grid", to: "/plan", shortcut: "Alt+1" },
  { key: "mise-en-place", label: "Preparação", shortLabel: "Preparo", icon: "lucide:scale", to: "/mise-en-place", shortcut: "Alt+2" },
  { key: "open", label: "Abertura", icon: "lucide:flame", to: "/", shortcut: "Alt+3" },
  { key: "close", label: "Fechamento", icon: "lucide:package-check", to: "/close", shortcut: "Alt+4" },
  { key: "quality", label: "Qualidade", icon: "lucide:badge-check", to: "/quality", shortcut: "Alt+5" },
];

export function stageSections({ qualityPending }: ProductionSectionsInput = {}): OperatorSection[] {
  return PRODUCTION_STAGES.map((stage) => {
    if (stage.key !== "quality" || !qualityPending) return { ...stage };
    return {
      ...stage,
      badge: String(qualityPending),
    };
  });
}

export function timersSection({ timersActive = 0, timersRinging = 0 }: ProductionSectionsInput = {}): OperatorSection {
  return {
    key: "timers",
    label: "Timers",
    icon: "lucide:alarm-clock",
    to: "/timers",
    ...(timersActive ? { badge: String(timersActive) } : {}),
    ...(timersRinging ? { attention: `${timersRinging} tocando` } : {}),
  };
}

/** O que não é etapa do fluxo: na tela de Ajustes (e no ⋯ do celular). */
export function toolSections({ canViewRecipes = false, canViewReports = false }: ProductionSectionsInput = {}): OperatorSection[] {
  const tools: OperatorSection[] = [];
  if (canViewRecipes) tools.push({ key: "recipes", label: "Receitas", icon: "lucide:book-open", to: "/recipes" });
  if (canViewReports) tools.push({ key: "reports", label: "Relatórios", icon: "lucide:table-2", to: "/reports" });
  tools.push({ key: "board", label: "Letreiro", icon: "lucide:tower-control", to: "/board" });
  return tools;
}

/**
 * Ajustes: um item só (v4 `plano-porque4.html`, Qualidade legenda 8), logo depois de
 * Timers. Receitas, Relatórios e o Letreiro moram na tela de Ajustes (`/settings`).
 */
export function settingsSection(): OperatorSection {
  return {
    key: "settings",
    label: "Ajustes",
    icon: "lucide:settings-2",
    to: "/settings",
    match: ["/recipes", "/reports", "/board"],
  };
}

/**
 * Rail (tablet deitado e desktop): o ciclo, um traço, Timers e Ajustes. O pé é o da
 * suíte (Avisos, Atalhos, Bloquear, iniciais), V6-KIT, R02.
 */
export function productionSections(input: ProductionSectionsInput = {}): OperatorSection[] {
  return [...stageSections(input), { ...timersSection(input), divider: true }, settingsSection()];
}

/**
 * Barra do polegar (celular e tablet em pé): o ciclo, os Timers e as ferramentas, na
 * ordem do rail. A barra mostra as quatro primeiras etapas; o resto (Qualidade, Timers,
 * Receitas, Relatórios, Letreiro) mora no "Mais" com o menu do operador (V6-KIT, T-08).
 */
export function phoneSections(input: ProductionSectionsInput = {}): OperatorSection[] {
  return productionSections(input);
}
