import { inject, provide, ref, type ComputedRef, type InjectionKey } from "vue";

import type { StationDeviceAgent } from "~/types/orders";
import {
  noPrinterReason,
  orderTicketPrintedMessage,
  stationPrints,
} from "~/presentation/orderTicket";
import {
  localDeviceAgentErrorMessage,
  printWithLocalDeviceAgent,
} from "../../../operator-kit/app/utils/localDeviceAgent";

interface OrderTicketResponse {
  payload_b64: string;
  title: string;
  reprint?: boolean;
}

/**
 * "Imprimir Via Pedido" no Gestor (P2-19 do mapa de cenários): o mesmo papel e a
 * mesma rota do PDV (`usePosOrderTickets.printOne`). O servidor compõe e carimba
 * (`OrderTicketEscposView`, permissão `shop.manage_orders`, a do Gestor); a página
 * relaia ao agente local desta estação, como a DANFE (`useDanfePrint`).
 *
 * Sem queda para `window.print()`, pelo mesmo motivo do PDV: a Via Pedido não tem
 * gêmea em HTML. Sem impressora, a falha é dita, nunca muda.
 */
export interface OrderTicketPrinter {
  agent: ComputedRef<StationDeviceAgent | null>;
  isPrinting: (ref: string) => boolean;
  print: (ref: string) => Promise<boolean>;
}

export const ORDER_TICKET_PRINTER: InjectionKey<OrderTicketPrinter> = Symbol("order-ticket-printer");

export function createOrderTicketPrinter(
  deviceAgent: ComputedRef<StationDeviceAgent | null>,
): OrderTicketPrinter {
  // Por pedido, não global: um toque num cartão não trava o menu de outro.
  const printing = ref<Set<string>>(new Set());
  const isPrinting = (ref_: string) => printing.value.has(ref_);

  async function print(ref_: string): Promise<boolean> {
    if (printing.value.has(ref_)) return false;
    const agent = deviceAgent.value;
    if (!stationPrints(agent)) {
      useSonner.error(`A Via Pedido do pedido ${ref_} não saiu. ${noPrinterReason(agent)}`);
      return false;
    }
    printing.value = new Set(printing.value).add(ref_);
    try {
      let job: OrderTicketResponse;
      try {
        job = await $fetch<OrderTicketResponse>(
          `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/ticket-escpos/`,
        );
      } catch (error) {
        useSonner.error(
          httpErrorMessage(error, `A Via Pedido do pedido ${ref_} não ficou pronta. Tente de novo.`),
        );
        return false;
      }
      try {
        await printWithLocalDeviceAgent(agent!, job.payload_b64, job.title);
      } catch (error) {
        useSonner.error(
          `A Via Pedido do pedido ${ref_} não saiu: ${localDeviceAgentErrorMessage(error)}`,
        );
        return false;
      }
      useSonner.success(orderTicketPrintedMessage(ref_, Boolean(job.reprint)));
      return true;
    } finally {
      const next = new Set(printing.value);
      next.delete(ref_);
      printing.value = next;
    }
  }

  return { agent: deviceAgent, isPrinting, print };
}

/** A tela que conhece a impressora da estação (o quadro, o detalhe) oferece o gesto. */
export function provideOrderTicketPrinter(
  deviceAgent: ComputedRef<StationDeviceAgent | null>,
): OrderTicketPrinter {
  const printer = createOrderTicketPrinter(deviceAgent);
  provide(ORDER_TICKET_PRINTER, printer);
  return printer;
}

/** O menu do pedido pergunta; sem quem ofereça, o item não aparece. */
export function useOrderTicketPrinter(): OrderTicketPrinter | null {
  return inject(ORDER_TICKET_PRINTER, null);
}
