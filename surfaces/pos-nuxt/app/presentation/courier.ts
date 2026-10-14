// O ENTREGADOR (TaOn) no balcão — a encomenda de entrega da casa (dono, 13/10/2026).
//
// A régua é do servidor: o bloco `courier` e as ações `courier-dispatch` /
// `courier-dispatch-again` são os MESMOS do Gestor (`order_queue._courier_block`),
// e a frase de cada estado também (`status_label`; na lista, `courier_label` com o
// tom). Aqui só se decide o que a tela mostra com o que veio.
import type { PreorderCard, PreorderCourier, PreorderEquipmentOption } from "~/types/preorders";

import { rowShowsSituation } from "./preorders";

export type CourierTone = "neutral" | "info" | "success" | "warning" | "danger";

/** A linha da corrida na lista, ou `null`. O "Saiu para entrega" que o selo de
 *  situação já diz não se repete ao lado dele. */
export function courierRowLine(
  card: Pick<PreorderCard, "courier_label" | "courier_tone" | "situation" | "situation_label">,
): { label: string; tone: CourierTone } | null {
  const label = (card.courier_label || "").trim();
  if (!label) return null;
  if (rowShowsSituation(card.situation) && label === card.situation_label) return null;
  return { label, tone: (card.courier_tone || "neutral") as CourierTone };
}

/** A cor do texto da linha da corrida na lista, por tom (o neutro, discreto). */
export const COURIER_TEXT: Record<CourierTone, string> = {
  neutral: "text-muted-foreground",
  info: "text-info",
  success: "text-success",
  warning: "text-warning",
  danger: "text-error",
};

/** O tom da corrida na cor do selo do Nuxt UI (`soft`). */
export function courierBadgeColor(tone: string | undefined): "neutral" | "info" | "success" | "warning" | "error" {
  if (tone === "danger") return "error";
  if (tone === "info" || tone === "success" || tone === "warning") return tone;
  return "neutral";
}

/** O painel do entregador aparece quando há o que dizer ou o que fazer: corrida
 *  pedida (qualquer estado), chamada sem resposta, falha, ou chamar agora. Antes
 *  de a encomenda poder sair, ele não ocupa a tela. */
export function courierPanelVisible(courier: PreorderCourier | null | undefined): boolean {
  if (!courier) return false;
  return Boolean(courier.status || courier.can_dispatch || courier.can_dispatch_again || courier.error);
}

/** O rótulo do gesto de chamar: o mesmo do Gestor. Depois de uma corrida que não
 *  terminou (ninguém aceitou, cancelada), é "Chamar outro entregador". */
export function courierCallLabel(courier: Pick<PreorderCourier, "status" | "attempts_count">): string {
  return courier.status || courier.attempts_count > 0 ? "Chamar outro entregador" : "Chamar entregador";
}

/** "Moto Honda CG · ABC1D23": o que o balcão confere quando o entregador chega. */
export function vehicleLine(driver: PreorderCourier["driver"]): string {
  if (!driver) return "";
  return [driver.vehicle_model, driver.vehicle_color, driver.vehicle_plate].filter(Boolean).join(" · ");
}

/** `tel:` só com os dígitos (e o +). */
export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, "")}`;
}

// ── A custódia da chamada (troco da gaveta, maquininha da casa) ───────────

/** As maquininhas livres para sair com o entregador. */
export function freeMachines(options: readonly PreorderEquipmentOption[]): PreorderEquipmentOption[] {
  return options.filter((opt) => opt.ref.startsWith("card_machine:") && opt.enabled !== false);
}

/** "maquininha Azul" (o rótulo pode já começar com "Maquininha"). */
export function machinePhrase(label: string): string {
  const clean = label.trim();
  if (!clean) return "maquininha";
  return clean.toLowerCase().startsWith("maquininha") ? clean[0]!.toLowerCase() + clean.slice(1) : `maquininha ${clean}`;
}

/** Sem maquininha livre: onde estão as que existem (o motivo é do servidor). */
export function noFreeMachineSentence(options: readonly PreorderEquipmentOption[]): string {
  const busy = options.filter((opt) => opt.ref.startsWith("card_machine:") && opt.reason);
  const where = busy.map((opt) => `${opt.label}: ${opt.reason}`).join(". ");
  return `${where ? `${where}. ` : "Nenhuma maquininha livre. "}Espere uma voltar para chamar.`;
}

/** Centavos → "20,00", o formato do campo de troco (o servidor lê vírgula). */
export function moneyInput(amountQ: number): string {
  const cents = Math.max(0, Math.round(amountQ));
  return `${Math.floor(cents / 100)},${String(cents % 100).padStart(2, "0")}`;
}

/** O corpo da chamada: só o que a chamada perguntou. */
export function custodyBody(
  custody: PreorderCourier["custody"],
  answer: { changeOut: string; machineRef: string },
): { change_out?: string; equipment?: string[] } {
  const asksChange = (custody?.change_out_suggested_q ?? 0) > 0;
  return {
    ...(asksChange ? { change_out: answer.changeOut.trim() || "0" } : {}),
    ...(custody?.needs_machine && answer.machineRef ? { equipment: [answer.machineRef] } : {}),
  };
}
