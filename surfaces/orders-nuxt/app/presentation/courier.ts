// Courier ride presentation — pure functions over the raw Machine status letter
// (D/G/P/A/S/E/F/N/C/U). The label text comes from the server projection
// (single source of truth); here we derive the compact step timeline and tones.

export type CourierTone = "muted" | "info" | "active" | "success" | "danger";

export interface CourierStep {
  key: "requested" | "accepted" | "picked_up" | "delivered";
  label: string;
  state: "done" | "current" | "pending";
}

/** Ride phases in board order. N/C (failed) short-circuit the timeline. */
const STEP_INDEX: Record<string, number> = {
  D: 0, // distribuindo
  G: 0, // aguardando aceite
  P: 0, // pendente (buscando entregador)
  U: 0, // agrupada — segue buscando/roteirizando
  A: 1, // aceita — entregador a caminho da loja
  S: 1, // em espera — entregador na loja
  E: 2, // em andamento — coletou, saiu para entrega
  F: 3, // finalizada
};

const STEPS: { key: CourierStep["key"]; label: string }[] = [
  { key: "requested", label: "Solicitado" },
  { key: "accepted", label: "Aceito" },
  { key: "picked_up", label: "Coletado" },
  { key: "delivered", label: "Entregue" },
];

export function courierFailed(letter: string): boolean {
  return letter === "N" || letter === "C";
}

/** Compact 4-step timeline for the ride panel. Empty for failed/blank status. */
export function courierSteps(letter: string): CourierStep[] {
  const idx = STEP_INDEX[letter];
  if (idx === undefined) return [];
  return STEPS.map((step, i) => ({
    ...step,
    state:
      i < idx
        ? "done"
        : i === idx
          ? letter === "F"
            ? "done"
            : "current"
          : "pending",
  }));
}

/** Visual tone for the ride status badge. */
export function courierTone(letter: string): CourierTone {
  if (courierFailed(letter)) return "danger";
  if (letter === "F") return "success";
  if (letter === "E") return "active";
  if (letter === "A" || letter === "S") return "info";
  if (letter === "D" || letter === "G" || letter === "P" || letter === "U")
    return "muted";
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
  const minutes = Math.max(1, Math.floor((nowMs - since) / 60_000));
  return `Pedido ${reminder.short_ref} em preparo há ${minutes} min. Já dá para chamar o entregador?`;
}

/** O detalhe do pedido abre com a confirmação de "Chamar entregador" já armada. */
export const COURIER_CALL_HASH = "#courier-call";
