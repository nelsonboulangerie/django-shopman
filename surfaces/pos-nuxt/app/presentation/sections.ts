// Presentation — as seções do PDV no shell da suíte (`OperatorSuiteShell`, fase 2).
// A barra lateral (mesa), a gaveta (☰) e a barra inferior (celular e tablet em pé)
// mostram as MESMAS seções: Comandas, Encomendas, Caixa e Tela do cliente; Ajustes
// depois de um traço; no pé, Terminal (a saúde da estação, com o sinal quando algo
// pede atenção). Avisos, Atalhos, Bloquear e o operador são o pé da suíte (kit).
// A barra inferior leva Comandas, Encomendas, Caixa e Fim do dia, e o "Mais" abre a
// gaveta com o resto.
//
// Puro: quem decide a contagem e a permissão é a Projection (comandas em uso, caixa
// aberto), a leitura das Encomendas (`usePosPreordersRail`) e a sonda do agente do
// balcão (`useAgentHealth`), lidas no shell (`usePosShell`).

import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";
import type { POSTabProjection } from "~/types/pos";

/** O estado geral do terminal (`terminalOverallStatus`), para o sinal do Terminal. */
export type PosTerminalStatus = "ready" | "warning" | "error";

/** O andar Ajustes do PDV: a porta (o item do pé do rail) e as rotas que moram nele. */
export const POS_SETTINGS_HOME = "/settings/seating";
export const POS_SETTINGS_ROUTES = ["/settings"];

export interface PosSectionsInput {
  tabs: readonly Pick<POSTabProjection, "state">[];
  hasOpenCashSession: boolean;
  preorders: { allowed: boolean; badge?: string };
  /** A saúde da estação; sem leitura ainda, sem sinal. */
  terminal?: PosTerminalStatus;
}

/** Comandas em uso: o número que o selo das Comandas conta. */
export function tabsInUse(tabs: readonly Pick<POSTabProjection, "state">[]): number {
  return tabs.filter((tab) => tab.state === "in_use").length;
}

export function posSections(input: PosSectionsInput): OperatorSection[] {
  const inUse = tabsInUse(input.tabs);
  const sections: OperatorSection[] = [
    {
      key: "board",
      label: "Comandas",
      icon: "lucide:receipt",
      // Sem `to`: na tela da venda, "Comandas" é um gesto da própria tela (volta ao
      // quadro guardando a comanda aberta), não uma navegação para a mesma rota.
      shortcut: "F2",
      badge: inUse > 0 ? String(inUse) : undefined,
      quick: true,
    },
  ];
  // Encomendas: só para quem lê pedidos; o selo conta as de hoje por entregar.
  if (input.preorders.allowed) {
    sections.push({
      key: "preorders",
      label: "Encomendas",
      icon: "lucide:calendar-clock",
      to: "/preorders",
      badge: input.preorders.badge,
      quick: true,
    });
  }
  sections.push(
    {
      key: "cash",
      label: "Caixa",
      icon: "lucide:wallet",
      to: "/session",
      quick: true,
      // Sem turno aberto, o ponto acende: a primeira venda do dia pede o fundo de troco.
      attention: input.hasOpenCashSession ? undefined : "caixa fechado, abrir",
    },
    // A Tela do cliente abre no segundo monitor: mora no rail, não no bolso (P27).
    {
      key: "display",
      label: "Tela do cliente",
      icon: "lucide:monitor-smartphone",
      where: "rail",
    },
    // Fim do dia (a contagem da vitrine e o fechamento, `pos-tablet4.html`): na barra de
    // baixo do tablet em pé e do celular; na barra lateral ele mora dentro do Caixa. A
    // tela é um corredor sem navegação (fora do shell), com "Sair" de volta ao Caixa.
    {
      key: "closing",
      label: "Fim do dia",
      icon: "lucide:clipboard-check",
      to: "/session/closing",
      where: "bar",
      quick: true,
    },
    // Ajustes no grupo de cima, depois de um traço, abaixo do Caixa (v4
    // `salao-mesas4.html`); na barra de baixo, no "Mais" (a gaveta).
    {
      key: "settings",
      label: "Ajustes",
      icon: "lucide:settings-2",
      to: POS_SETTINGS_HOME,
      match: POS_SETTINGS_ROUTES,
      divider: true,
    },
    // Terminal no pé: a saúde da estação (impressora, gaveta, agente, fiscal), com o
    // sinal quando algo pede atenção. Leva à aba Terminal dos Ajustes, onde estão o
    // diagnóstico e o caminho de conserto.
    {
      key: "terminal",
      label: "Terminal",
      icon: "lucide:monitor-cog",
      to: "/settings/terminal",
      where: "rail",
      foot: true,
      ...terminalSignal(input.terminal),
    },
  );
  return sections;
}

function terminalSignal(status?: PosTerminalStatus): Pick<OperatorSection, "attention" | "tone"> {
  if (status === "error") return { attention: "com erro", tone: "error" };
  if (status === "warning") return { attention: "pede atenção", tone: "warning" };
  return {};
}

/**
 * A seção acesa para a rota. Pela rota, e não pelo `to` de cada seção: Comandas não
 * tem `to` (é gesto da tela da venda), e o Terminal mora dentro dos Ajustes.
 */
export function posCurrentSection(path: string): string {
  if (path.startsWith("/session")) return "cash";
  if (path.startsWith("/preorders")) return "preorders";
  if (path.startsWith("/settings")) return "settings";
  return "board";
}

/**
 * As telas-corredor (WP-FASE2 §7): Fim do dia e o Relatório de caixa sobem sem barra
 * lateral e sem barra inferior. Quem entra num corredor sai pelo "Sair" (ou o voltar)
 * dele, de volta ao Caixa.
 */
export function posCorridorRoute(path: string): boolean {
  return path.startsWith("/session/closing") || path.startsWith("/session/report");
}
