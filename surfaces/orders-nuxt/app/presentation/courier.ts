// A corrida no painel: funções puras sobre o estado da corrida no vocabulário da
// casa (`ride_state`, o `RideState` do servidor), igual para qualquer serviço. A
// frase vem do servidor (`status_label`); aqui saem os passos e o tom.

export type CourierTone = "muted" | "info" | "active" | "success" | "danger";

export interface CourierStep {
  key: "requested" | "accepted" | "picked_up" | "delivered";
  label: string;
  state: "done" | "current" | "pending";
}

/** Os passos na ordem do quadro. Não atendida e cancelada não têm passos. */
const STEP_INDEX: Record<string, number> = {
  searching: 0, // procurando quem leve
  grouped: 0, // juntou com outra corrida
  reassigning: 0, // trocando de entregador
  assigned: 1, // alguém aceitou, a caminho da loja
  at_store: 1, // na loja
  on_route: 2, // coletou, saiu para entrega
  done: 3, // entregue
};

const STEPS: { key: CourierStep["key"]; label: string }[] = [
  { key: "requested", label: "Solicitado" },
  { key: "accepted", label: "Aceito" },
  { key: "picked_up", label: "Coletado" },
  { key: "delivered", label: "Entregue" },
];

export function courierFailed(state: string): boolean {
  return state === "not_served" || state === "cancelled";
}

/** Compact 4-step timeline for the ride panel. Empty for failed/blank status. */
export function courierSteps(state: string): CourierStep[] {
  const idx = STEP_INDEX[state];
  if (idx === undefined) return [];
  return STEPS.map((step, i) => ({
    ...step,
    state:
      i < idx
        ? "done"
        : i === idx
          ? state === "done"
            ? "done"
            : "current"
          : "pending",
  }));
}

/** Visual tone for the ride status badge. */
export function courierTone(state: string): CourierTone {
  if (courierFailed(state)) return "danger";
  if (state === "done") return "success";
  if (state === "on_route") return "active";
  if (state === "assigned" || state === "at_store") return "info";
  return "muted";
}

/** Badge classes per tone (Tailwind design tokens already in the app). */
export function courierToneBadge(tone: CourierTone): string {
  switch (tone) {
    case "danger":
      return "border-error/40 bg-error/10 text-error";
    case "success":
      return "border-success/40 bg-success/10 text-success";
    case "active":
      return "border-primary/40 bg-primary/10 text-primary";
    case "info":
      return "border-info/40 bg-info/10 text-info";
    default:
      return "border-border bg-muted text-muted-foreground";
  }
}

/** O lembrete temporário de chamar o entregador, como o servidor o projeta. */
export interface CourierReminder {
  due_at_iso: string;
  since_iso: string;
  since_basis: string;
  short_ref: string;
  /** `preparing` · `ready` (pronto, no balcão) · `retry` (a última corrida terminou sem entregador). */
  stage?: string;
}

/**
 * A frase do lembrete quando ele já vale (o relógio passou de `due_at_iso`), ou `null`.
 * "Pedido 0042 em preparo há 10 min. Já dá para chamar o entregador?" — os minutos
 * contam do início do preparo e andam com o relógio da tela.
 */
export function courierReminderLine(
  reminder: CourierReminder | null | undefined,
  nowMs: number,
): string | null {
  if (!reminder) return null;
  const due = Date.parse(reminder.due_at_iso);
  const since = Date.parse(reminder.since_iso);
  if (!Number.isFinite(due) || !Number.isFinite(since) || nowMs < due)
    return null;
  if (reminder.stage === "retry")
    return `Pedido ${reminder.short_ref} continua sem entregador. Chamar de novo?`;
  if (reminder.stage === "ready")
    return `Pedido ${reminder.short_ref} está pronto e sem entregador. Chamar agora?`;
  const minutes = Math.max(1, Math.floor((nowMs - since) / 60_000));
  return `Pedido ${reminder.short_ref} em preparo há ${minutes} min. Já dá para chamar o entregador?`;
}

/** O detalhe do pedido abre com a confirmação de "Chamar entregador" já armada. */
export const COURIER_CALL_HASH = "#courier-call";
