/**
 * Catálogo de um canal externo no Gestor: as abas da página e o rótulo de uma
 * captura do inventário. A página faz três trabalhos diferentes (organizar
 * categorias, cadastrar complementos, revisar vínculos); cada um é uma aba.
 */
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
  const when = new Date(snapshot.captured_at);
  const shown = Number.isNaN(when.getTime())
    ? snapshot.captured_at
    : new Intl.DateTimeFormat("pt-BR", {
        timeZone: "America/Sao_Paulo",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
        .format(when)
        .replace(",", "");
  const ads = snapshot.item_count === 1 ? "anúncio" : "anúncios";
  return `Captura nº ${snapshot.id} · ${shown} · ${snapshot.context} · ${snapshot.item_count} ${ads}`;
}
