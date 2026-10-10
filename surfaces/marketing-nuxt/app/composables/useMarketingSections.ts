// As seções do Marketing, numa fonte só: a barra lateral e a gaveta (`OperatorSuiteShell`),
// a barra inferior do celular e a faixa de sub-seções de Ajustes leem daqui.
//
// Decisão do dono (03/10/2026, SUITE-UX §6): o andar de OPERAÇÃO tem Decisões,
// Agendados e Enviados; Ajustes entra por um item só, no pé da barra lateral, longe da
// operação, como no Gestor.
//
// Fase 2 (WP-FASE2-UX-OPERADOR, A4): Ajustes é uma seção com rota própria, `/settings`
// (a página que lista as quatro sub-seções, como os Ajustes do Gestor), e cada
// sub-seção mora embaixo dela: `/settings/campaigns`, `/settings/templates`,
// `/settings/offers` e `/settings/platforms`. Dentro de uma sub-seção, a faixa da
// toolbar (`MarketingSettingsNav`) leva às outras três sem voltar.
//
// Barra inferior (regra única do kit, `quickBarLayout`): as quatro seções declaram
// `quick`; sem seção de fora, não há "Mais" (o ☰ abre a gaveta com o menu completo).
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

export type MarketingSectionKey = "decisions" | "scheduled" | "sent" | "settings";
export type MarketingSettingsKey = "campaigns" | "templates" | "offers" | "platforms";

export const MARKETING_SETTINGS_ROOT = "/settings";

export const MARKETING_SETTINGS_SECTIONS: ReadonlyArray<{
  key: MarketingSettingsKey;
  label: string;
  icon: string;
  to: string;
  /** O que mora ali, numa frase (a página de Ajustes lista, não esconde). */
  description: string;
}> = [
  {
    key: "campaigns",
    label: "Campanhas",
    icon: "lucide:megaphone",
    to: "/settings/campaigns",
    description: "O que dispara um anúncio, quando e para quem",
  },
  {
    key: "templates",
    label: "Modelos",
    icon: "lucide:file-text",
    to: "/settings/templates",
    description: "Os textos e as fotos que as campanhas usam",
  },
  {
    key: "offers",
    label: "Ofertas e cupons",
    icon: "lucide:ticket-percent",
    to: "/settings/offers",
    description: "Descontos e cupons que um anúncio pode levar",
  },
  {
    key: "platforms",
    label: "Plataformas",
    icon: "lucide:radio-tower",
    to: "/settings/platforms",
    description: "Instagram, Facebook, Google e WhatsApp: conexão e formato",
  },
];

export function marketingSectionFor(path: string): MarketingSectionKey {
  if (path === "/" || path.startsWith("/announcements")) return "decisions";
  if (path.startsWith("/second-control")) return "decisions";
  if (path === "/scheduled") return "scheduled";
  if (path === "/history") return "sent";
  return "settings";
}

export function marketingSettingsFor(path: string): MarketingSettingsKey | null {
  const entry = MARKETING_SETTINGS_SECTIONS.find(
    (section) => path === section.to || path.startsWith(`${section.to}/`),
  );
  return entry?.key ?? null;
}

export function useMarketingSections() {
  const route = useRoute();
  const { decisionCount } = useMarketingDecisions();

  const activeSection = computed<MarketingSectionKey>(() =>
    marketingSectionFor(route.path),
  );
  const activeSettings = computed<MarketingSettingsKey | null>(() =>
    marketingSettingsFor(route.path),
  );

  const sections = computed<OperatorSection[]>(() => [
    {
      key: "decisions",
      label: "Decisões",
      icon: "lucide:inbox",
      to: "/",
      match: ["/announcements", "/second-control"],
      group: "Operação",
      quick: true,
      badge: decisionCount.value ? String(decisionCount.value) : undefined,
    },
    {
      key: "scheduled",
      label: "Agendados",
      icon: "lucide:calendar-clock",
      to: "/scheduled",
      group: "Operação",
      quick: true,
    },
    {
      key: "sent",
      label: "Enviados",
      icon: "lucide:send",
      to: "/history",
      group: "Operação",
      quick: true,
    },
    {
      key: "settings",
      label: "Ajustes",
      icon: "lucide:settings-2",
      to: MARKETING_SETTINGS_ROOT,
      match: [MARKETING_SETTINGS_ROOT],
      foot: true,
      quick: true,
    },
  ]);

  return {
    activeSection,
    activeSettings,
    sections,
    settingsSections: MARKETING_SETTINGS_SECTIONS,
  };
}
