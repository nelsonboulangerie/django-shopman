// Presentation — Tab Board shaping (spec §2.3).
//
// Pure transforms over the tabs Projection: ordering, the in-use/all filter,
// and the per-tab card view. Status labels and totals come pre-resolved from
// the serializer (Arc 1 E3/E4); this module only orders and composes them into
// the shape the board renders. No availability or price arithmetic.

import type { POSTabProjection } from "~/types/pos";
import { normalizeSearchText } from "~/presentation/catalog";

export type TabFilter = "all" | "in_use";

/**
 * Filtro do board pelo campo de referência: o que o operador digita ali também
 * FILTRA os cards (nome do cliente ou ref, sem exigir acento) — antes o filtro
 * rico só existia dentro do seletor de comandas.
 */
export function filterTabsByQuery(tabs: POSTabProjection[], query: string): POSTabProjection[] {
  const normalized = normalizeSearchText((query || "").trim());
  if (!normalized) return tabs;
  return tabs.filter((tab) =>
    [tab.display_ref, tab.ref, tab.customer_name]
      .some((value) => normalizeSearchText(String(value || "")).includes(normalized)),
  );
}

/** A comanda que a cozinha terminou: a que pede o balcão agora. */
export function isKitchenReady(tab: POSTabProjection): boolean {
  return tab.state === "in_use" && tab.item_count > 0 && Boolean(tab.kitchen_ready);
}

/** "Tudo pronto" primeiro (o balcão chama o cliente), depois as em uso, depois as livres;
 *  dentro de cada grupo, pela referência (numeric-aware, pt-BR). */
export function sortTabs(tabs: POSTabProjection[]): POSTabProjection[] {
  const rank = (tab: POSTabProjection) => (isKitchenReady(tab) ? 0 : tab.state === "in_use" ? 1 : 2);
  return [...tabs].sort((a, b) =>
    rank(a) - rank(b)
      || a.display_ref.localeCompare(b.display_ref, "pt-BR", { numeric: true }),
  );
}

/**
 * As comandas que FICARAM prontas desde a leitura anterior (por `session_key`).
 * `previous` nulo é a primeira leitura: o que já estava pronto ao abrir a tela
 * não toca, só o que muda com ela aberta.
 */
export function newlyReadyTabs(previous: ReadonlySet<string> | null, tabs: POSTabProjection[]): {
  ready: Set<string>;
  fresh: string[];
} {
  const ready = new Set(tabs.filter(isKitchenReady).map((tab) => tab.session_key).filter(Boolean));
  const fresh = previous ? [...ready].filter((key) => !previous.has(key)) : [];
  return { ready, fresh };
}

export function filterTabs(tabs: POSTabProjection[], filter: TabFilter): POSTabProjection[] {
  return filter === "in_use" ? tabs.filter((tab) => tab.state === "in_use") : tabs;
}

export function countOpenTabs(tabs: POSTabProjection[]): number {
  return tabs.filter((tab) => tab.state === "in_use").length;
}

export interface TabCardView {
  ref: string;
  displayRef: string;
  isInUse: boolean;
  isFree: boolean;
  /** Fired to the kitchen and not yet paid — the loud state of the board. */
  isUnpaid: boolean;
  /** Has items but nothing sent to the kitchen yet — a quiet "a enviar" cue. */
  pendingKitchen: boolean;
  /** A cozinha terminou tudo: "Tudo pronto", o selo mais alto do quadro. */
  kitchenReady: boolean;
  statusLabel: string;
  /** Customer name, falling back to an items preview; empty when there is neither. */
  identity: string;
  /** Line summary: item count + total; empty for a tab without items. */
  summary: string;
  selected: boolean;
}

/** O selo de estado do cartão de comanda: um só por cartão, na ordem do que o
 *  balcão precisa fazer primeiro. Todo estado sai no MESMO selo (NuxtBadge soft do
 *  tema, um tamanho); só cor, ícone e texto mudam. O ícone é o que fica no cartão
 *  estreito, com `label` no aria e `title` na dica. */
export interface TabCardBadge {
  kind: "ready" | "unpaid" | "pending" | "status";
  label: string;
  title: string;
  color: "success" | "warning" | "neutral";
  icon: string;
}

export function tabCardBadge(view: TabCardView): TabCardBadge {
  if (view.kitchenReady) {
    return { kind: "ready", label: "Tudo pronto", title: "Tudo pronto: a cozinha terminou tudo desta comanda", color: "success", icon: "lucide:bell-ring" };
  }
  if (view.isUnpaid) {
    return { kind: "unpaid", label: "Não pago", title: "Não pago: enviado à cozinha e ainda não pago", color: "warning", icon: "lucide:credit-card" };
  }
  if (view.pendingKitchen) {
    return { kind: "pending", label: "A enviar", title: "A enviar: tem itens ainda não enviados à cozinha", color: "neutral", icon: "lucide:utensils" };
  }
  const label = view.statusLabel || (view.isInUse ? "Em uso" : "Livre");
  return {
    kind: "status",
    label,
    title: view.isInUse ? `${label}: comanda aberta, sem itens` : `${label}: comanda disponível`,
    color: "neutral",
    icon: view.isInUse ? "lucide:circle-dot" : "lucide:circle-dashed",
  };
}

/**
 * Shape a free-text tab reference for input: strip control chars and the
 * channel's disallowed characters, collapse whitespace, and clamp to the
 * channel's max length. The allowed set comes from the tab-lifecycle capability
 * (Projection-driven) — this only enforces the shape, never the policy.
 */
export function sanitizeTabRef(
  value: string,
  options: { maxLength: number; disallowedChars: string[] },
): string {
  const disallowed = new Set(options.disallowedChars);
  return String(value || "")
    .replace(/[\r\n\t]/g, "")
    .split("")
    .filter((char) => !disallowed.has(char))
    .join("")
    .replace(/\s+/g, " ")
    .slice(0, options.maxLength);
}

export function tabCardView(tab: POSTabProjection, selectedRef = ""): TabCardView {
  const isInUse = tab.state === "in_use";
  const hasItems = tab.item_count > 0;
  return {
    ref: tab.ref,
    displayRef: tab.display_ref,
    isInUse,
    isFree: !hasItems,
    // Comanda SEM item não pode estar "não paga": o selo saía junto com "Livre"
    // no mesmo cartão (comanda que disparou à cozinha e depois perdeu as linhas
    // mantém `fired_lines` no dado). A linha de baixo já guardava por `hasItems`;
    // esta esquecia.
    isUnpaid: hasItems && Boolean(tab.fired),
    pendingKitchen: hasItems && !tab.fired,
    kitchenReady: isKitchenReady(tab),
    statusLabel: tab.status_label,
    // O cartão sem item não repete o selo (dono, 13/10/2026): "Livre" mora SÓ no selo,
    // e o corpo fica vazio em vez de dizer "Livre" de novo e "Comanda livre".
    identity: tab.customer_name || tab.items_preview || "",
    summary: hasItems
      ? `${tab.item_count} ${tab.item_count === 1 ? "item" : "itens"} · ${tab.total_display}`
      : "",
    selected: Boolean(selectedRef) && tab.ref === selectedRef,
  };
}
