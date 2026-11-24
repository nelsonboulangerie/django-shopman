import { ref, type ComputedRef } from "vue";

import type { StationDeviceAgent } from "~/types/orders";
import { stationPrints } from "~/presentation/orderTicket";
import {
  retentionNoPrinterReason,
  retentionReceiptPrintedMessage,
} from "~/presentation/retentionReceipt";
import {
  localDeviceAgentErrorMessage,
  printWithLocalDeviceAgent,
} from "../../../operator-kit/app/utils/localDeviceAgent";

interface RetentionReceiptResponse {
  payload_b64: string;
  title: string;
  reprint?: boolean;
}

/**
 * O recibo do valor retido (#3538): o servidor compõe e carimba
 * (`OrderRetentionReceiptEscposView`, permissão `shop.manage_orders`); a página
 * relaia ao agente local desta estação, como a Via Pedido (`useOrderTicketPrint`).
 *
 * Sem queda para `window.print()`: o papel não tem gêmeo em HTML no Gestor, e o
 * cliente já tem o mesmo recibo no link do pedido. Sem impressora, a falha é dita.
 */
export function useRetentionReceiptPrint(deviceAgent: ComputedRef<StationDeviceAgent | null>) {
  const printing = ref(false);

  async function print(ref_: string): Promise<boolean> {
    if (printing.value) return false;
    const agent = deviceAgent.value;
    if (!stationPrints(agent)) {
      useSonner.error(`O recibo do valor retido do pedido ${ref_} não saiu. ${retentionNoPrinterReason(agent)}`);
      return false;
    }
    printing.value = true;
    try {
      let job: RetentionReceiptResponse;
      try {
        // POST: compor é emitir a via, e o servidor carimba a primeira.
        job = await $fetch<RetentionReceiptResponse>(
          `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/retention-receipt-escpos/`,
          { method: "POST" },
        );
      } catch (error) {
        useSonner.error(
          httpErrorMessage(error, `O recibo do valor retido do pedido ${ref_} não ficou pronto. Tente de novo.`),
        );
        return false;
      }
      try {
        await printWithLocalDeviceAgent(agent!, job.payload_b64, job.title);
      } catch (error) {
        useSonner.error(
          `O recibo do valor retido do pedido ${ref_} não saiu: ${localDeviceAgentErrorMessage(error)}`,
        );
        return false;
      }
      useSonner.success(retentionReceiptPrintedMessage(ref_, Boolean(job.reprint)));
      return true;
    } finally {
      printing.value = false;
    }
  }

  return { printing, print };
}
