import type { ComputedRef } from "vue";
import { toast } from "vue-sonner";

import type { POSProjection } from "~/types/pos";
import { ticketCountLabel } from "~/presentation/orderTickets";
import type { PrintPlan } from "~/presentation/preorders";

/**
 * A Via Pedido: uma, ou o lote do que a tela das Encomendas mostra, na bobina.
 *
 * O desenho é o mesmo do recibo e da DANFE (`pages/index.vue`): o SERVIDOR
 * compõe os bytes ESC/POS, esta camada só relaia ao agente do balcão. O lote
 * sai num trabalho só — os bytes já vêm concatenados, com o corte parcial entre
 * uma via e a seguinte.
 *
 * ⚠️ **Não há queda para `window.print()` aqui, e é deliberado.** No recibo a
 * queda existe porque há um recibo DESENHADO na tela para o diálogo do
 * navegador imprimir. A Via Pedido não tem gêmea em HTML, e inventar uma criaria
 * um segundo leiaute com um segundo dono — exatamente o que a docstring do
 * `receipt_escpos` proíbe ("se cada máquina compusesse, dois balcões
 * imprimiriam diferente"). Então a falha é ALTA e explicada, nunca silenciosa:
 * o operador fica sabendo que esta estação não tem impressora e o que fazer.
 */
interface TicketPrintResponse {
  payload_b64: string;
  title: string;
  count?: number;
  reprint_count?: number;
}

export function usePosOrderTickets(pos: ComputedRef<POSProjection | null>) {
  const apiPath = useApiPath();
  const agent = useCounterAgent(pos);

  const printing = ref(false);
  const printingRef = ref("");

  /** A queda avisada: sem agente, dizer o que falta em vez de falhar mudo. */
  function warnNoAgent() {
    toast.error(
      `Esta estação não imprime: ${agent.printUnavailableReason.value} `
      + "A Via Pedido sai no balcão que tem impressora.",
    );
  }

  async function fetchPrintable(path: string, params?: Record<string, string>) {
    return await $fetch<TicketPrintResponse>(apiPath(path), {
      credentials: "include",
      query: params,
    });
  }

  /**
   * O lote do que está VISÍVEL: o período da tela, recortado pelos refs que os
   * filtros deixaram. Cada pedido é carimbado no servidor (a próxima sai 2ª via).
   */
  async function printBatch(plan: PrintPlan): Promise<boolean> {
    if (!import.meta.client || printing.value || !plan.refs.length) return false;
    if (!agent.canPrint.value) {
      warnNoAgent();
      return false;
    }
    printing.value = true;
    try {
      const job = await fetchPrintable("/api/v1/backstage/orders/tickets/escpos/", {
        date_from: plan.date_from,
        date_to: plan.date_to,
        refs: plan.refs.join(","),
      });
      const outcome = await agent.print(job.payload_b64, job.title);
      if (outcome.status !== "printed") {
        toast.error(`As vias não saíram: ${outcome.detail || "o agente do balcão não respondeu"}.`);
        return false;
      }
      const reimpressas = job.reprint_count || 0;
      toast.success(
        `${ticketCountLabel(job.count ?? plan.refs.length)} na bobina.`
        + (reimpressas ? ` ${reimpressas} saíram marcadas como 2ª via.` : ""),
      );
      return true;
    } catch (error) {
      toast.error(`${httpErrorMessage(error, "O servidor não montou as vias.")} Nada saiu na bobina. Tente de novo.`);
      return false;
    } finally {
      printing.value = false;
    }
  }

  /** Uma via só — a que caiu, a que rasgou, a que chegou agora. */
  async function printOne(ref: string): Promise<boolean> {
    if (!import.meta.client || printingRef.value) return false;
    if (!agent.canPrint.value) {
      warnNoAgent();
      return false;
    }
    printingRef.value = ref;
    try {
      const job = await fetchPrintable(
        `/api/v1/backstage/orders/${encodeURIComponent(ref)}/ticket-escpos/`,
      );
      const outcome = await agent.print(job.payload_b64, job.title);
      if (outcome.status !== "printed") {
        toast.error(`A Via Pedido de ${ref} não saiu: ${outcome.detail || "o agente do balcão não respondeu"}.`);
        return false;
      }
      toast.success(`Via Pedido de ${ref} na bobina.`);
      return true;
    } catch (error) {
      toast.error(`${httpErrorMessage(error, "O servidor não montou a Via Pedido.")} Nada saiu na bobina. Tente de novo.`);
      return false;
    } finally {
      printingRef.value = "";
    }
  }

  return {
    printing,
    printingRef,
    hasPrinter: agent.canPrint,
    printerUnavailableReason: agent.printUnavailableReason,
    printBatch,
    printOne,
  };
}
