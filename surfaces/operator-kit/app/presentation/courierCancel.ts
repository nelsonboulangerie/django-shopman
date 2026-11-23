// O cancelamento pedido de uma corrida da TaOn, como aviso de tela. O estado vem
// do servidor (`courier.cancel_state`, a mesma fonte no Gestor e no PDV):
//  - `pending`: pedido enviado, a TaOn ainda não confirmou (espera, não é erro);
//  - `unknown`: o envio ficou sem resposta (confere-se na central antes de reenviar);
//  - `failed`: a TaOn recusou, ou nada foi enviado. A corrida segue aberta.
// A frase também é do servidor; aqui só se escolhe a cor e o ícone do aviso.

/** O que a projeção manda (`courier.cancel_state` no pedido). */
export interface CourierCancelState {
  state: string;
  message: string;
  at: string;
}

export interface CourierCancelNotice {
  color: "info" | "warning" | "error";
  icon: string;
  message: string;
}

/** O aviso, ou `null` quando não há cancelamento pedido. */
export function courierCancelNotice(
  state: string | null | undefined,
  message: string | null | undefined,
): CourierCancelNotice | null {
  if (!state || !message) return null;
  if (state === "pending") return { color: "info", icon: "i-lucide-hourglass", message };
  if (state === "unknown") return { color: "warning", icon: "i-lucide-circle-help", message };
  return { color: "error", icon: "i-lucide-triangle-alert", message };
}


/** Um motivo de cancelamento que a confirmação oferece: o botão já é o `reason_id`. */
export interface CancelReason {
  id: number;
  label: string;
  icon: string;
}

/** A confirmação de "Cancelar corrida", com as frases do servidor. */
export interface CancelConfirmation {
  /** "Cancelar a corrida B? A05 e C12 voltam para Aguardando." */
  question: string;
  /** "Cancelar a corrida B" */
  confirmLabel: string;
  /** Depois do aceite: "Por que cancelar a corrida B?" */
  reasonQuestion: string;
  /** "A05 e C12 voltam para Aguardando." */
  consequence: string;
  /** Vazio antes do aceite (a central só aceita um motivo, e ninguém escolhe). */
  reasons: CancelReason[];
}

/** O ícone de cada motivo que a casa oferece (`order_queue.COURIER_CANCEL_REASONS`). */
const CANCEL_REASON_ICONS: Record<number, string> = {
  12: "i-lucide-user-x",
  37: "i-lucide-timer-off",
  40: "i-lucide-phone-off",
};

/**
 * Lê `Action.confirmation` do "Cancelar corrida", a MESMA no Gestor e no PDV. O
 * servidor manda as frases (`courier_cancel_confirmation`); aqui só se dá forma,
 * sem inventar motivo: entrada sem `id` inteiro ou sem rótulo não vira botão.
 */
export function cancelConfirmation(
  action: { confirmation?: unknown; label?: string } | null | undefined,
): CancelConfirmation {
  const raw = (action?.confirmation ?? {}) as Record<string, unknown>;
  const text = (value: unknown) => (typeof value === "string" ? value : "");
  const reasons = (Array.isArray(raw.reasons) ? raw.reasons : [])
    .map((item) => item as { id?: unknown; label?: unknown })
    .filter((item) => Number.isInteger(item.id) && text(item.label))
    .map((item) => ({
      id: item.id as number,
      label: text(item.label),
      icon: CANCEL_REASON_ICONS[item.id as number] ?? "i-lucide-ban",
    }));
  return {
    question: text(raw.description) || "Cancelar a corrida?",
    confirmLabel: text(raw.confirm_label) || action?.label || "Cancelar corrida",
    reasonQuestion: text(raw.reason_question) || "Por que cancelar a corrida?",
    consequence: text(raw.consequence),
    reasons,
  };
}
