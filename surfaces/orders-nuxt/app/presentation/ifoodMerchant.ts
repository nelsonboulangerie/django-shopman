// A loja no iFood, ao vivo — frases e cores puras, testáveis sem runtime.
// Copy: inequívoco primeiro (docs/reference/omotenashi-copy.md). O gestor precisa
// saber, sem completar sentido, o que o iFood respondeu AGORA.
import type {
  IFoodInterruptionRow,
  IFoodMerchantDetail,
  IFoodOpeningHours,
} from "~/types/ifoodMerchant";

type BadgeColor = "success" | "warning" | "error" | "neutral";

/** Cor do estado da operação (OK, WARNING, CLOSED, UNAVAILABLE, ERROR). */
export function operationColor(state: string): BadgeColor {
  if (state === "OK") return "success";
  if (state === "WARNING") return "warning";
  if (state === "CLOSED" || state === "UNAVAILABLE") return "neutral";
  if (state === "ERROR") return "error";
  return "neutral";
}

/** Cor de uma validação do status: só o que não está OK chama atenção. */
export function checkColor(state: string): BadgeColor {
  return state === "OK" ? "success" : operationColor(state);
}

/** A linha de cima da disponibilidade. */
export function availabilityLine(detail: IFoodMerchantDetail): string {
  if (detail.status_error) return "";
  if (detail.available === null) return "O iFood não informou a disponibilidade.";
  return detail.available
    ? "O iFood está recebendo pedidos desta loja."
    : "O iFood NÃO está recebendo pedidos desta loja.";
}

/** "21/11 11h às 21/11 11h30" — o intervalo da pausa. */
export function pausePeriod(pause: IFoodInterruptionRow): string {
  if (!pause.ends_at_display) return `desde ${pause.starts_at_display}`;
  return `${pause.starts_at_display} até ${pause.ends_at_display}`;
}

/** O que fazer com a pausa: removê-la aqui (Portal) ou ligar o iFood de novo (Gestor). */
export function pauseHint(pause: IFoodInterruptionRow): string {
  if (pause.removable) return "";
  if (pause.origin === "calendar")
    return "Sai sozinha quando o dia deixa de estar fechado no calendário da loja.";
  return "Para tirar, ligue o iFood de novo no botão acima.";
}

/** A linha de cima do horário: iguais, diferentes ou sem resposta. */
export function hoursLine(hours: IFoodOpeningHours): string {
  if (hours.error) return "";
  if (!hours.governs)
    return "A casa não declarou horário semanal: o horário do iFood segue o do Portal do Parceiro.";
  return hours.matches
    ? "O horário no iFood é igual ao da casa."
    : "O horário no iFood está diferente do da casa. Salvar o horário no Admin grava de novo.";
}
