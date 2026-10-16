// Presentation — a conferência das sacolas no despacho (P1-13 dos cenários).
//
// Cada Via Pedido leva um QR de conferência, `VP-<pedido>-<k>-<N>-<assinatura>`
// (`shop/services/volume_check.py`). O leitor do posto Saída bipa a sacola e o
// servidor responde o que achou. Aqui mora o que a tela faz com a resposta: qual
// pedido está em conferência, a frase da faixa e o aviso forte da sacola errada.
// Nada disto segura a saída: a conferência só avisa.

import type { CodeFormat } from "../../../operator-kit/app/presentation/codeScan";
import { splitRef } from "./board";

/** O código curto que o balcão fala ("U68"), o mesmo do cartão. */
const short = (ref: string) => splitRef(ref).code;

export const VOLUME_CODE: CodeFormat = {
  prefix: "VP-",
  pattern: /^VP-.+-\d{1,2}-\d{1,2}-[A-Z2-7]{8}$/,
  maxLength: 96,
};

export type VolumeCheckOutcome = "checked" | "repeated" | "other_order" | "stale" | "unknown";

/** A resposta de `POST orders/volume-check/`. */
export interface VolumeCheckResponse {
  outcome: VolumeCheckOutcome;
  message: string;
  order_ref: string;
  expected_ref: string;
  volume: number;
  volumes: number;
  checked: number;
  total: number;
  complete: boolean;
}

/** O pedido em conferência, e o que a faixa mostra dele. */
export interface Conference {
  ref: string;
  checked: number;
  total: number;
}

/** O último aviso da faixa: forte (sacola de outro pedido) ou de atenção. */
export interface ConferenceAlarm {
  tone: "error" | "warning";
  message: string;
  /** A sacola errada: o pedido a que ela pertence (para "Conferir este"). */
  otherRef?: string;
}

export interface ConferenceState {
  conference: Conference | null;
  alarm: ConferenceAlarm | null;
}

export const EMPTY_CONFERENCE: ConferenceState = { conference: null, alarm: null };

/**
 * O pedido que a próxima bipada confere. Com um pedido FIXO (o detalhe aberto),
 * é ele. No quadro, é o da conferência em curso, enquanto ela não terminou; a
 * conferência que terminou não prende a próxima sacola (é outro pedido saindo).
 */
export function expectedRef(state: ConferenceState, fixedRef = ""): string {
  if (fixedRef) return fixedRef;
  const current = state.conference;
  // `total` 0: acabou de trocar de pedido ("Conferir este") e ainda não bipou.
  return current && (current.total === 0 || current.checked < current.total) ? current.ref : "";
}

/** O estado da faixa depois de uma resposta do servidor. */
export function applyResult(state: ConferenceState, result: VolumeCheckResponse): ConferenceState {
  switch (result.outcome) {
    case "checked":
    case "repeated":
      return {
        conference: { ref: result.order_ref, checked: result.checked, total: result.total },
        alarm: result.outcome === "repeated"
          ? {
              tone: "warning",
              message: `A sacola ${result.volume} de ${result.total} do pedido ${short(result.order_ref)} já foi conferida.`,
            }
          : null,
      };
    case "other_order":
      return {
        conference: state.conference,
        alarm: {
          tone: "error",
          message:
            `Esta sacola é do pedido ${short(result.order_ref)}, não do ${short(result.expected_ref)}. ` +
            "Separe-a antes de entregar.",
          otherRef: result.order_ref,
        },
      };
    case "stale":
      return {
        conference: state.conference,
        alarm: {
          tone: "warning",
          message:
            `Esta via diz ${result.volumes} ${result.volumes === 1 ? "sacola" : "sacolas"}, e o pedido ` +
            `${short(result.order_ref)} tem ${result.total}. Reimprima as vias do pedido.`,
        },
      };
    default:
      return { conference: state.conference, alarm: { tone: "warning", message: result.message } };
  }
}

/** "Conferindo o pedido X: 2 de 3 sacolas", ou "todas as 3 sacolas conferidas". */
export function conferenceLine(conference: Conference): string {
  const code = short(conference.ref);
  if (!conference.total) return `Conferindo o pedido ${code}: bipe as sacolas dele.`;
  if (conference.checked >= conference.total) {
    return conference.total === 1
      ? `Pedido ${code}: sacola conferida.`
      : `Pedido ${code}: todas as ${conference.total} sacolas conferidas.`;
  }
  return `Conferindo o pedido ${code}: ${conference.checked} de ${conference.total} sacolas.`;
}

/** A etiqueta da conferência no cartão: só existe quando alguém já bipou. */
export function cardCheckBadge(card: {
  volumes_checked?: number;
  volumes_to_check?: number;
}): { label: string; complete: boolean } | null {
  const checked = card.volumes_checked ?? 0;
  const total = card.volumes_to_check ?? 0;
  if (!checked || !total) return null;
  if (checked >= total) return { label: total === 1 ? "Sacola conferida" : "Sacolas conferidas", complete: true };
  return { label: `${checked} de ${total} conferidas`, complete: false };
}
