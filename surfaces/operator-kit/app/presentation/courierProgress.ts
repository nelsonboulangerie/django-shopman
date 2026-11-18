// O ANDAMENTO da corrida da TaOn, em frases (Gestor e PDV leem o mesmo bloco
// `courier` do servidor, `order_queue._courier_block`).
//
// O servidor manda instantes ISO (`pickup_eta_at`, `delivery_eta_at`,
// `arrived_pickup_at`, `sync_since`); os minutos se contam aqui, com o relógio
// da tela, para a frase andar sozinha entre uma leitura e outra. Hierarquia: o
// estado em palavra é o selo (`status_label`); abaixo dele, quando chega para
// coletar e quando a entrega está prevista; e, se a TaOn parou de informar, o
// aviso de desde quando.

import { STORE_TIME_ZONE } from "./dates";
import { formatClock } from "./clock";

export interface CourierProgressInput {
  status: string;
  pickup_eta_at?: string;
  arrived_pickup_at?: string;
  delivery_eta_at?: string;
  sync_since?: string;
  /** O entregador desistiu e a TaOn procura outro para a MESMA corrida (`courier.reopen_view`). */
  reopened_at?: string;
  reopened_driver?: string;
}

export interface CourierProgressView {
  /** "Chega para coletar em ~7 min", "Chega para coletar a qualquer momento" ou "Chegou à loja às 15:50". */
  pickup: string;
  /** "Entrega prevista ~16:05". */
  delivery: string;
  /** "A TaOn não informa a corrida desde 15h42." (vazio com a leitura em dia). */
  stale: string;
  /**
   * A corrida segue chamada, sem ninguém a caminho e sem nada a fazer:
   * "Diego desistiu às 14:32. A TaOn já procura outro." ou
   * "A TaOn juntou com outra corrida. Ela já tem entregador."
   */
  waiting: string;
}

const EMPTY: CourierProgressView = { pickup: "", delivery: "", stale: "", waiting: "" };

/** O que a TaOn faz depois da desistência: a mesma corrida, outro entregador. */
export const REOPENED_HINT = "A TaOn já procura outro";

/** A TaOn juntou a corrida a outra, que já tem entregador (letra U). */
export const GROUPED_TITLE = "A TaOn juntou com outra corrida";
export const GROUPED_HINT = "Ela já tem entregador";

/** "Diego desistiu às 14:32" (sem o nome: "O entregador desistiu às 14:32"). */
export function withdrawalTitle(driver: string | null | undefined, atMs: number): string {
  return `${driver?.trim() || "O entregador"} desistiu às ${clockHHMM(atMs)}`;
}

function epoch(iso: string | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

/** "15h50", no fuso da loja (o dispositivo pode estar em outro). */
export function clockHHMM(ms: number): string {
  return formatClock(new Date(ms), STORE_TIME_ZONE);
}

export function courierProgress(
  courier: CourierProgressInput | null | undefined,
  nowMs: number,
): CourierProgressView {
  if (!courier?.status) return EMPTY;
  const ended = ["F", "N", "C"].includes(courier.status);
  const view = { ...EMPTY };

  const sync = epoch(courier.sync_since);
  if (sync !== null && !ended)
    view.stale = `A TaOn não informa a corrida desde ${clockHHMM(sync)}.`;

  const reopened = epoch(courier.reopened_at);
  if (courier.status === "U") view.waiting = `${GROUPED_TITLE}. ${GROUPED_HINT}.`;
  else if (reopened !== null && !ended)
    view.waiting = `${withdrawalTitle(courier.reopened_driver, reopened)}. ${REOPENED_HINT}.`;

  const arrived = epoch(courier.arrived_pickup_at);
  const pickupEta = epoch(courier.pickup_eta_at);
  if (courier.status === "A" || courier.status === "S") {
    if (arrived !== null) view.pickup = `Chegou à loja às ${clockHHMM(arrived)}`;
    else if (pickupEta !== null) {
      const minutes = Math.ceil((pickupEta - nowMs) / 60_000);
      view.pickup =
        minutes >= 1
          ? `Chega para coletar em ~${minutes} min`
          : "Chega para coletar a qualquer momento";
    }
  }

  const deliveryEta = epoch(courier.delivery_eta_at);
  if (deliveryEta !== null && !ended)
    view.delivery = `Entrega prevista ~${clockHHMM(deliveryEta)}`;
  return view;
}
