// A loja no iFood, ao vivo: frases, cores e avisos, puros e testáveis sem runtime.
// Copy: inequívoco primeiro (docs/reference/omotenashi-copy.md). A tela responde UMA
// pergunta do operador antes de tudo: "o iFood está recebendo pedidos agora?".
import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";
import type {
  IFoodInterruptionRow,
  IFoodMerchantDetail,
  IFoodMerchants,
  IFoodOpeningHours,
  IFoodStatusCheck,
} from "~/types/ifoodMerchant";

type Tone = "success" | "warning" | "error" | "neutral";

/** O bloco do topo: a resposta, o motivo em uma linha, a cor e o ícone. */
export interface StoreHeadline {
  title: string;
  reason: string;
  tone: Tone;
  icon: string;
  badge: string;
}

export function storeHeadline(detail: IFoodMerchantDetail): StoreHeadline {
  if (detail.status_error || detail.available === null) {
    return {
      title: "Não deu para saber se o iFood está recebendo pedidos",
      reason: detail.status_error || "O iFood não informou a disponibilidade.",
      tone: "neutral",
      icon: "i-lucide-circle-help",
      badge: "Sem resposta",
    };
  }
  const op = detail.operations[0];
  const reason = op ? [op.title, op.description].filter(Boolean).join(": ") : "";
  if (detail.available) {
    return {
      title: "O iFood está recebendo pedidos",
      reason: reason || "Loja aberta no iFood.",
      tone: "success",
      icon: "i-lucide-circle-check",
      badge: "Aberta",
    };
  }
  return {
    title: "O iFood não está recebendo pedidos",
    reason: reason || "Loja fechada no iFood.",
    tone: "warning",
    icon: "i-lucide-circle-pause",
    badge: "Fechada",
  };
}

/** "Teste - Nelson Boulangerie · loja de teste": a loja deste app, numa linha. */
export function merchantLine(
  merchants: IFoodMerchants | null,
  detail: IFoodMerchantDetail | null,
): string {
  const current = merchants?.merchants.find((m) => m.is_current);
  if (!current) return "";
  const isTest = detail?.detail.some(
    (row) => row.label === "Loja de teste" && row.value === "Sim",
  );
  return isTest ? `${current.name} · loja de teste` : current.name;
}

/** Ícone e cor de uma validação do status (sem o id técnico à vista). */
export function checkLook(check: IFoodStatusCheck): { icon: string; tone: Tone } {
  switch (check.state) {
    case "OK":
      return { icon: "i-lucide-circle-check", tone: "success" };
    case "WARNING":
      return { icon: "i-lucide-triangle-alert", tone: "warning" };
    case "ERROR":
      return { icon: "i-lucide-circle-x", tone: "error" };
    default:
      return { icon: "i-lucide-circle-pause", tone: "warning" };
  }
}

/** Classe de cor do texto para um tom (só as do tema). */
export function toneText(tone: Tone): string {
  return {
    success: "text-success",
    warning: "text-warning",
    error: "text-error",
    neutral: "text-muted",
  }[tone];
}

/** "21/11 11h até 21/11 11h30" — o intervalo da pausa. */
export function pausePeriod(pause: IFoodInterruptionRow): string {
  if (!pause.ends_at_display) return `desde ${pause.starts_at_display}`;
  return `${pause.starts_at_display} até ${pause.ends_at_display}`;
}

/** De onde veio a pausa, e a descrição só quando diz algo a mais. */
export function pauseOrigin(pause: IFoodInterruptionRow): string {
  return pause.description && pause.description !== pause.origin_label
    ? `${pause.origin_label}: ${pause.description}`
    : pause.origin_label;
}

/** A pausa que o iFood aceitou e a lista dele ainda não mostra. */
export function pauseListingNote(pause: IFoodInterruptionRow): string {
  return pause.listed_by_ifood
    ? ""
    : "O iFood aceitou esta pausa, mas a lista de pausas dele ainda não a mostra.";
}

/** Como a pausa sai: removendo aqui (Portal) ou ligando o iFood de novo (Gestor). */
export function pauseHint(pause: IFoodInterruptionRow): string {
  if (pause.removable) return "";
  if (pause.origin === "calendar")
    return "Sai sozinha quando o dia deixa de estar fechado no calendário da loja.";
  return "Sai quando o iFood é ligado de novo.";
}

/** Dias em que o iFood e a casa discordam. */
export function divergentDays(hours: IFoodOpeningHours): string[] {
  return hours.days.filter((d) => !d.matches).map((d) => d.label);
}

/** O aviso do horário: diferente (com a gravação pronta) ou esperando o iFood mostrar. */
export function hoursAlert(
  hours: IFoodOpeningHours,
  onWrite: () => void,
): OperatorScreenAlert | null {
  if (hours.error || !hours.governs || hours.matches !== false) return null;
  const days = divergentDays(hours);
  const which = days.length ? ` (${days.join(", ").toLowerCase()})` : "";
  if (hours.written_recently) {
    return {
      id: `hours-wait:${hours.written_at_display}`,
      color: "info",
      icon: "i-lucide-clock",
      title: `Horário gravado no iFood ${hours.written_at_display}`,
      description: `O iFood confirmou a gravação e leva alguns minutos para mostrar o horário novo${which}.`,
      action: { label: "Gravar de novo", onSelect: onWrite },
    };
  }
  return {
    id: `hours-diff:${days.join(",")}`,
    color: "warning",
    icon: "i-lucide-calendar-clock",
    title: "O horário no iFood está diferente do da casa",
    description: `Dias diferentes${which}. Gravar manda ao iFood o horário da casa.`,
    action: { label: "Gravar no iFood", onSelect: onWrite },
  };
}
