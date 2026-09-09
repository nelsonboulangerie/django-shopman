export type MarketingVitalName = "LCP" | "INP" | "CLS";
export type MarketingVitalRating = "good" | "needs_improvement" | "poor";
export type MarketingRoute =
  | "board"
  | "campaigns"
  | "templates"
  | "platforms"
  | "history"
  | "announcement_detail"
  | "other";

export interface MarketingVital {
  name: MarketingVitalName;
  value: number;
  rating: MarketingVitalRating;
  route: MarketingRoute;
  theme: "light" | "dark";
}

const ENDPOINT = "/api/v1/backstage/marketing/telemetry/vital/";

export function marketingRoute(pathname: string): MarketingRoute {
  const path = pathname.split("?", 1)[0]?.split("#", 1)[0]?.replace(/\/+$/, "") || "/";
  if (path === "/") return "board";
  if (path === "/campaigns") return "campaigns";
  if (path === "/templates") return "templates";
  if (path === "/platforms") return "platforms";
  if (path === "/history") return "history";
  if (/^\/announcements\/[^/]+$/.test(path)) return "announcement_detail";
  return "other";
}

export function marketingVitalRating(name: MarketingVitalName, value: number): MarketingVitalRating {
  const good = name === "LCP" ? 2500 : name === "INP" ? 200 : 0.1;
  const poor = name === "LCP" ? 4000 : name === "INP" ? 500 : 0.25;
  if (value <= good) return "good";
  if (value <= poor) return "needs_improvement";
  return "poor";
}

export function buildMarketingVital(
  name: MarketingVitalName,
  value: number,
  pathname: string,
  dark: boolean,
): MarketingVital | null {
  if (!Number.isFinite(value) || value < 0 || value > 120_000) return null;
  const normalized = Math.round(value * 1000) / 1000;
  return {
    name,
    value: normalized,
    rating: marketingVitalRating(name, normalized),
    route: marketingRoute(pathname),
    theme: dark ? "dark" : "light",
  };
}

export async function reportMarketingVital(sample: MarketingVital): Promise<boolean> {
  try {
    await $fetch(ENDPOINT, { method: "POST", body: sample });
    return true;
  } catch {
    return false;
  }
}
