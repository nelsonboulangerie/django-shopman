// As seções do Marketing, numa fonte só: a barra do topo (`CampaignTopBar`) e a
// barra do polegar no celular (`MarketingSectionBar`) leem as mesmas quatro.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

export type MarketingSectionKey = "decisions" | "scheduled" | "sent" | "settings";
export type MarketingSettingsKey = "campaigns" | "templates" | "offers" | "platforms";

export function useMarketingSections() {
  const route = useRoute();
  const { decisionCount } = useMarketingDecisions();

  const activeSection = computed<MarketingSectionKey>(() => {
    const path = route.path;
    if (path === "/" || path.startsWith("/announcements")) return "decisions";
    if (path === "/scheduled") return "scheduled";
    if (path === "/history") return "sent";
    // O panorama antigo (`/v2` sem área, ou Hoje) continua acessível pela URL e
    // pertence ao andar de operação, não aos ajustes.
    if (path === "/v2") {
      const area = String(route.query.area || "today");
      return area === "today" ? "decisions" : "settings";
    }
    return "settings";
  });

  const activeSettings = computed<MarketingSettingsKey>(() => {
    if (route.path === "/templates") return "templates";
    if (route.path === "/platforms") return "platforms";
    if (route.path === "/campaigns") return "campaigns";
    const area = String(route.query.area || "");
    if (area === "offers" || area === "platforms") return area;
    return "campaigns";
  });

  const sections = computed<OperatorSection[]>(() => [
    {
      key: "decisions",
      label: "Decisões",
      icon: "lucide:inbox",
      to: "/",
      attention: decisionCount.value ? String(decisionCount.value) : undefined,
    },
    {
      key: "scheduled",
      label: "Agendados",
      icon: "lucide:calendar-clock",
      to: "/scheduled",
    },
    {
      key: "sent",
      label: "Enviados",
      icon: "lucide:send",
      to: "/history",
    },
    {
      key: "settings",
      label: "Ajustes",
      icon: "lucide:sliders-horizontal",
      to: "/v2?area=campaigns",
      match: ["/campaigns", "/templates", "/platforms"],
    },
  ]);

  return { activeSection, activeSettings, sections };
}
