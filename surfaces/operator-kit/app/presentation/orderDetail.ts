// Presentation — o detalhe de UM pedido, comum ao Gestor e ao PDV.
//
// Transformações puras sobre a parte comum do contrato (`types/orderDetail.ts`).
// O servidor já manda tudo pronto para a tela (rótulos em português, ações com a
// régua resolvida); aqui só se decide a FORMA: o tom da cor, a linha que junta
// fatos sem separador órfão, e se um bloco tem o que mostrar.
import type {
  OperatorOrderDetail,
  OrderDetailAction,
  OrderDetailCustomerProfile,
} from "../types/orderDetail";

// ── Tom (cor funcional; o cromo fica neutro) ────────────────────────────────

export type Tone = "info" | "warning" | "success" | "danger" | "neutral";

const STATUS_TONE: Record<string, Tone> = {
  new: "info",
  accepted: "info",
  preparing: "warning",
  ready: "success",
  dispatched: "info",
  delivered: "success",
  completed: "success",
  cancelled: "danger",
  returned: "neutral",
};

/** O tom do status do pedido (o ciclo é do servidor; aqui só a cor). */
export function statusTone(status: string): Tone {
  return STATUS_TONE[status] ?? "neutral";
}

/** Classes do selo (borda + tinta + texto) para um tom. Calmo por padrão; só
 *  perigo/atenção/sucesso carregam cor saturada. Pinta com o token do tema
 *  (`operator-theme.css`), nunca com a paleta: o tema dá a cada tom a cor que
 *  passa AA como texto sobre o próprio fundo /10, no claro e no escuro, e o
 *  selo fica igual no Gestor e no PDV. */
export function toneBadge(tone: Tone | string): string {
  switch (tone) {
    case "danger":
      return "border-destructive/40 bg-destructive/10 text-destructive";
    case "warning":
      return "border-warning/40 bg-warning/10 text-warning";
    case "success":
      return "border-success/40 bg-success/10 text-success";
    case "info":
      return "border-info/40 bg-info/10 text-info";
    default:
      return "border-border bg-muted text-muted-foreground";
  }
}

// ── Ícones ──────────────────────────────────────────────────────────────────

/** A projeção fala a ligadura do Material Symbols (ela também serve o Admin);
 *  as telas de operador falam lucide. A tradução mora aqui, uma vez. */
const MATERIAL_TO_LUCIDE: Record<string, string> = {
  language: "globe",
  chat: "message-circle",
  fastfood: "utensils-crossed",
  storefront: "store",
  shopping_bag: "shopping-bag",
  local_shipping: "bike",
  store: "store",
  restaurant: "utensils",
  takeout_dining: "shopping-bag",
  pedal_bike: "bike",
  two_wheeler: "bike",
};

export function lucideIcon(name: string): string {
  return MATERIAL_TO_LUCIDE[name] || name || "circle";
}

// ── Linhas ─────────────────────────────────────────────────────────────────

/** Junta fatos com " · ", deixando de fora os que faltam — nunca um separador
 *  órfão, nunca "R$ 0,00" no lugar de "ainda não sabemos". */
export function joinFacts(...parts: (string | null | undefined)[]): string {
  return parts
    .map((part) => (part ?? "").trim())
    .filter(Boolean)
    .join(" · ");
}

/** "12 pedidos · última compra há 12 dias" — só com o que o servidor sabe. */
export function profileHistory(profile: OrderDetailCustomerProfile | null): string {
  if (!profile) return "";
  return joinFacts(
    profile.orders_label,
    profile.last_order_display ? `última compra ${profile.last_order_display}` : "",
  );
}

/** "ticket médio R$ 42,00 · costuma levar Pão francês". */
export function profileHabits(profile: OrderDetailCustomerProfile | null): string {
  if (!profile) return "";
  return joinFacts(
    profile.average_ticket_display ? `ticket médio ${profile.average_ticket_display}` : "",
    profile.favorite_product ? `costuma levar ${profile.favorite_product}` : "",
  );
}

/** Até quando o código do iFood leva à pessoa ("Vale até 14:32"). Depois disso a
 *  central não repassa. Vazio quando não há prazo legível. */
export function relayExpiresLabel(iso: string): string {
  if (!iso) return "";
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  return `Vale até ${at.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
}

/** O cadastro do cliente no Admin — o CRUD de cliente ainda mora lá. Vazio sem
 *  cliente identificado ou sem endereço do Admin configurado. */
export function customerAdminUrl(adminBaseUrl: string, customerRef: string): string {
  if (!customerRef || !adminBaseUrl) return "";
  return `${adminBaseUrl}/admin/guestman/customer/?q=${encodeURIComponent(customerRef)}`;
}

/** Há alguma forma de alcançar a pessoa? Sem nenhuma, o bloco não aparece —
 *  vale mais uma tela honesta do que uma fileira de botões que não levam a nada. */
export function hasCustomerContact(order: OperatorOrderDetail, adminUrl: string): boolean {
  return Boolean(
    order.customer_phone_uri ||
      order.customer_relay_phone ||
      order.customer_whatsapp_url ||
      order.customer_email ||
      adminUrl,
  );
}

/** Link de documento fiscal: a projeção usa `href` (e o legado de terceiros, `url`). */
export function fiscalHref(link: { href?: string; url?: string }): string {
  return link.href || link.url || "#";
}

// ── Ações ──────────────────────────────────────────────────────────────────

/** A ação `ref` que o servidor ofereceu para este pedido, se ofereceu. */
export function detailAction(order: Pick<OperatorOrderDetail, "actions"> | null | undefined, ref: string): OrderDetailAction | undefined {
  return order?.actions?.find((action) => action.ref === ref);
}

/** Comentar no histórico: só quando o servidor oferece e deixa (o contexto e a
 *  permissão são dele — o balcão e o Gestor comentam pela mesma rota). */
export function canComment(order: Pick<OperatorOrderDetail, "actions"> | null | undefined): boolean {
  return Boolean(detailAction(order, "comment")?.enabled);
}
