// Presentation — as seções do PDV na camada visual da suíte (onda V4, prévia
// `pos-sale4.html`). O rail da suíte (tablet e desktop) e a barra do polegar
// (celular) mostram as MESMAS seções, nesta ordem: Comandas (F2), Encomendas,
// Caixa e Tela do cliente. No pé, Ajustes (V5-SALAO, prévia `salao-mesas4.html`: o
// andar do cadastro, separado da operação; hoje com o Salão). Terminal, Avisos,
// Atalhos, Bloquear e o operador moram no pé do rail, montados pelo `PosFunctionRail`.
//
// Puro: quem decide a contagem e a permissão é a Projection (comandas em uso, caixa
// aberto) e a leitura das Encomendas (`usePosPreordersRail`).

import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";
import type { POSTabProjection } from "~/types/pos";

/** A tela de trabalho em que se está, para acender a seção certa. */
export type PosView = "board" | "sale" | "checkout" | "session" | "preorders" | "settings";

/** O andar Ajustes do PDV: a porta (o item do pé do rail) e as rotas que moram nele. */
export const POS_SETTINGS_HOME = "/settings/seating";
export const POS_SETTINGS_ROUTES = ["/settings"];

export interface PosSectionsInput {
  tabs: readonly Pick<POSTabProjection, "state">[];
  hasOpenCashSession: boolean;
  preorders: { allowed: boolean; badge?: string; ariaLabel?: string };
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
      shortcut: "F2",
      badge: inUse > 0 ? String(inUse) : undefined,
      badgeLabel: inUse > 0 ? (inUse === 1 ? "1 comanda em uso" : `${inUse} comandas em uso`) : undefined,
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
      badgeLabel: input.preorders.badge ? input.preorders.ariaLabel?.replace(/^Encomendas: /, "") : undefined,
    });
  }
  sections.push(
    {
      key: "cash",
      label: "Caixa",
      icon: "lucide:wallet",
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
    // baixo do tablet em pé e do celular; no rail ele mora dentro do Caixa.
    {
      key: "closing",
      label: "Fim do dia",
      icon: "lucide:clipboard-check",
      to: "/session/closing",
      where: "bar",
    },
    // Ajustes no grupo de cima, depois de um traço, abaixo do Caixa (v4
    // `salao-mesas4.html`); na barra de baixo, no "Mais".
    {
      key: "settings",
      label: "Ajustes",
      icon: "lucide:settings-2",
      to: POS_SETTINGS_HOME,
      match: POS_SETTINGS_ROUTES,
      divider: true,
    },
  );
  return sections;
}

/** A seção acesa para cada tela de trabalho. */
export function posCurrentSection(view: PosView): string {
  if (view === "session") return "cash";
  if (view === "preorders") return "preorders";
  if (view === "settings") return "settings";
  return "board";
}
