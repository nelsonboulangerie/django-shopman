/**
 * Catálogo de um canal externo no Gestor: as abas da página e o rótulo de uma
 * captura do inventário. A página faz três trabalhos diferentes (organizar
 * categorias, cadastrar complementos, revisar vínculos); cada um é uma aba.
 */
import { formatDateClock } from "../../../operator-kit/app/presentation/clock";

export type ChannelCatalogTab = "categories" | "addons" | "bindings";

export function channelCatalogTabs(channel: string) {
  return [
    { label: "Categorias", value: "categories", icon: "i-lucide-list-tree" },
    ...(channel === "ifood"
      ? [{ label: "Complementos", value: "addons", icon: "i-lucide-list-plus" }]
      : []),
    { label: "Itens no iFood", value: "bindings", icon: "i-lucide-link-2" },
  ] as { label: string; value: ChannelCatalogTab; icon: string }[];
}

export function pickChannelCatalogTab(
  value: unknown,
  channel: string,
): ChannelCatalogTab {
  const known = channelCatalogTabs(channel).map((tab) => tab.value);
  return known.includes(value as ChannelCatalogTab)
    ? (value as ChannelCatalogTab)
    : "categories";
}

/** "Captura nº 1 · 17/11/2026 12:26 · DEFAULT · 9 anúncios" (hora de Brasília). */
export function snapshotLabel(snapshot: {
  id: number;
  captured_at: string;
  context: string;
  item_count: number;
}): string {
  const shown =
    formatDateClock(
      snapshot.captured_at,
      { day: "2-digit", month: "2-digit", year: "numeric" },
      { timeZone: "America/Sao_Paulo", joiner: " " },
    ) || snapshot.captured_at;
  const ads = snapshot.item_count === 1 ? "anúncio" : "anúncios";
  return `Captura nº ${snapshot.id} · ${shown} · ${snapshot.context} · ${snapshot.item_count} ${ads}`;
}
