// As seções do Marketing, numa fonte só: o rail da suíte (tablet e desktop), a barra
// do polegar (celular) e a segunda linha de Ajustes leem daqui.
//
// Decisão do dono (03/10/2026, SUITE-UX §6): o andar de OPERAÇÃO tem quatro seções,
// Decisões, Agendados, Enviados e Ajustes, e o andar de AJUSTES entra por um item só,
// com as próprias seções numa segunda linha (Campanhas, Modelos, Ofertas e cupons,
// Plataformas). Na camada visual da suíte (V4-MKT), Ajustes mora no pé do rail, longe
// da operação, como no Gestor.
//
// Um nome por lugar (`depois-navegacao.jpg`): cada seção de Ajustes é uma rota própria,
// `/campaigns`, `/templates`, `/offers` e `/platforms`.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

export type MarketingSectionKey = "decisions" | "scheduled" | "sent" | "settings";
export type MarketingSettingsKey = "campaigns" | "templates" | "offers" | "platforms";

export const MARKETING_SETTINGS_SECTIONS: ReadonlyArray<{
  key: MarketingSettingsKey;
  label: string;
  icon: string;
  to: string;
}> = [
  { key: "campaigns", label: "Campanhas", icon: "lucide:megaphone", to: "/campaigns" },
  { key: "templates", label: "Modelos", icon: "lucide:file-text", to: "/templates" },
  { key: "offers", label: "Ofertas e cupons", icon: "lucide:ticket-percent", to: "/offers" },
  { key: "platforms", label: "Plataformas", icon: "lucide:radio-tower", to: "/platforms" },
];

/** "3 esperando você": o que o selo de Decisões conta, por extenso. */
export function decisionBadgeLabel(count: number): string {
  return count === 1 ? "1 esperando você" : `${count} esperando você`;
}

export function useMarketingSections() {
  const route = useRoute();
  const { decisionCount } = useMarketingDecisions();

  const activeSection = computed<MarketingSectionKey>(() => {
    const path = route.path;
    if (path === "/" || path.startsWith("/announcements")) return "decisions";
    if (path === "/scheduled") return "scheduled";
    if (path === "/history") return "sent";
    if (path.startsWith("/second-control")) return "decisions";
    return "settings";
  });

  const activeSettings = computed<MarketingSettingsKey>(() => {
    if (route.path === "/templates") return "templates";
    if (route.path === "/platforms") return "platforms";
    if (route.path === "/offers") return "offers";
    return "campaigns";
  });

  const sections = computed<OperatorSection[]>(() => [
    {
      key: "decisions",
      label: "Decisões",
      icon: "lucide:inbox",
      to: "/",
      group: "Operação",
      badge: decisionCount.value ? String(decisionCount.value) : undefined,
      badgeLabel: decisionCount.value ? decisionBadgeLabel(decisionCount.value) : undefined,
    },
    {
      key: "scheduled",
      label: "Agendados",
      icon: "lucide:calendar-clock",
      to: "/scheduled",
      group: "Operação",
    },
    {
      key: "sent",
      label: "Enviados",
      icon: "lucide:send",
      to: "/history",
      group: "Operação",
    },
    {
      key: "settings",
      label: "Ajustes",
      icon: "lucide:settings-2",
      to: "/campaigns",
      match: ["/campaigns", "/templates", "/offers", "/platforms"],
      foot: true,
    },
  ]);

  return { activeSection, activeSettings, sections, settingsSections: MARKETING_SETTINGS_SECTIONS };
}
