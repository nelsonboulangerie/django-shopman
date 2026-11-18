// Presentation — "O que falta neste pedido" (WP-G05). Puro.
//
// Quem decide o que falta, em que tom e com qual gesto é o servidor
// (`shopman/backstage/projections/order_pending.py`). Aqui só se traduz a lista em
// desenho: o ícone e a palavra de cada tom, o peso de cada botão e a linha do dinheiro
// que já voltou. Nenhuma régua de negócio mora neste arquivo.
import type {
  CancelledMoneyProjection,
  OrderPendingActionProjection,
  OrderPendingProjection,
} from "~/generated/ordersContract";

export type PendingTone = "error" | "warning" | "info";

/** O tom da linha; o que a tela não conhece vira o mais calmo, nunca alarme. */
export function pendingTone(tone: string): PendingTone {
  return tone === "error" || tone === "warning" ? tone : "info";
}

/** O ícone, a cor do ícone e a palavra que o leitor de tela ouve antes do fato. */
export const PENDING_TONES: Record<
  PendingTone,
  { icon: string; iconClass: string; spoken: string }
> = {
  error: {
    icon: "lucide:circle-alert",
    iconClass: "text-error",
    spoken: "Precisa de alguém",
  },
  warning: {
    icon: "lucide:triangle-alert",
    iconClass: "text-warning",
    spoken: "Confira",
  },
  // Espera que se resolve sozinha: ampulheta, sem cor de erro (P2-26).
  info: { icon: "lucide:hourglass", iconClass: "text-muted", spoken: "Em espera" },
};

const ACTION_ICONS: Record<string, string> = {
  "requeue-fiscal": "i-lucide-refresh-cw",
  "resend-payment-link": "i-lucide-send",
  "print-danfe": "i-lucide-printer",
  "contact-customer": "i-lucide-message-circle",
  cancel: "i-lucide-ban",
};

export interface PendingButton {
  ref: string;
  label: string;
  icon: string;
  color: "primary" | "neutral" | "error";
  variant: "solid" | "outline";
  disabled: boolean;
  /** Por que não pode agora: aparece escrito, não só no `title`. */
  blockedReason: string;
  /** Só a conversa com o cliente: abre fora do Gestor. */
  href: string;
}

export interface PendingButtonState {
  /** Uma gravação do pedido em andamento: nenhum gesto de gravar aceita toque. */
  busy: boolean;
  /** A DANFE deste pedido está sendo enviada à impressora. */
  danfePrinting: boolean;
}

/**
 * O botão de uma ação da pendência. Um gesto principal na faixa inteira: o primeiro da
 * primeira linha que pede alguém (`lead`). O resto é secundário. Cancelar é sempre
 * vermelho, como no menu do pedido.
 */
export function pendingButton(
  action: OrderPendingActionProjection,
  options: PendingButtonState & { lead: boolean },
): PendingButton {
  const printing = action.ref === "print-danfe" && options.danfePrinting;
  const isLink = action.ref === "contact-customer";
  return {
    ref: action.ref,
    label: printing ? "Imprimindo…" : action.label,
    icon: ACTION_ICONS[action.ref] ?? "i-lucide-arrow-right",
    color: action.ref === "cancel" ? "error" : options.lead ? "primary" : "neutral",
    variant: options.lead ? "solid" : "outline",
    disabled: !action.enabled || printing || (!isLink && options.busy),
    blockedReason: action.enabled ? "" : action.reason,
    href: isLink ? action.href : "",
  };
}

export interface PendingLine {
  key: string;
  tone: PendingTone;
  icon: string;
  iconClass: string;
  spoken: string;
  label: string;
  reason: string;
  buttons: PendingButton[];
  /** Os motivos das ações que não podem agora, escritos sob a linha. */
  blockedReasons: string[];
}

/** As linhas da faixa, na ordem do servidor, com os botões já pesados. */
export function pendingLines(
  pending: readonly OrderPendingProjection[],
  state: PendingButtonState,
): PendingLine[] {
  // O gesto principal é o da primeira linha que pede alguém; espera não tem principal.
  const leadKey = pending.find(
    (item) => pendingTone(item.tone) !== "info" && item.actions.length,
  )?.key;
  return pending.map((item) => {
    const tone = pendingTone(item.tone);
    const buttons = item.actions.map((action, index) =>
      pendingButton(action, {
        ...state,
        lead: item.key === leadKey && index === 0,
      }),
    );
    return {
      key: item.key,
      tone,
      ...PENDING_TONES[tone],
      label: item.label,
      reason: item.reason,
      buttons,
      blockedReasons: [
        ...new Set(buttons.map((button) => button.blockedReason).filter(Boolean)),
      ],
    };
  });
}

/**
 * O dinheiro do cancelado que JÁ está onde devia ("Estornado", "Nada foi cobrado"): não
 * é pendência, é a resposta a "e o dinheiro?". O que ainda não fechou (estorno pedido,
 * estorno que não saiu) vem do servidor como linha da lista, e aqui devolve `null`.
 */
export function settledMoney(
  money: CancelledMoneyProjection | null | undefined,
): { title: string; customerLine: string } | null {
  if (!money?.settled) return null;
  return {
    title: `Dinheiro do pedido cancelado: ${money.label}`,
    customerLine: money.customer_line
      ? `O cliente lê na loja: “${money.customer_line}”`
      : "",
  };
}
