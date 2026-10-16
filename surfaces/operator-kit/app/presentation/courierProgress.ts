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

export interface CourierProgressInput {
  status: string;
  pickup_eta_at?: string;
  arrived_pickup_at?: string;
  delivery_eta_at?: string;
  sync_since?: string;
}

export interface CourierProgressView {
  /** "Chega para coletar em ~7 min", "Chega para coletar a qualquer momento" ou "Chegou à loja às 15:50". */
  pickup: string;
  /** "Entrega prevista ~16:05". */
  delivery: string;
  /** "A TaOn não informa a corrida desde 15:42." (vazio com a leitura em dia). */
  stale: string;
}

const EMPTY: CourierProgressView = { pickup: "", delivery: "", stale: "" };

function epoch(iso: string | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

/** "15:50", no fuso da loja (o dispositivo pode estar em outro). */
export function clockHHMM(ms: number): string {
  return new Date(ms).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: STORE_TIME_ZONE,
  });
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
