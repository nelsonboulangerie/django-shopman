import type { ComputedRef } from "vue";
import { toast } from "vue-sonner";

import type { POSProjection } from "~/types/pos";
import {
  canPrintBatch,
  isoDate,
  resolveRange,
  type TicketPreset,
  type TicketRange,
  type TicketRow,
} from "~/presentation/orderTickets";

/**
 * As filipetas do painel: escolher o intervalo, conferir o lote, mandar à bobina.
 *
 * O desenho é o mesmo do recibo e da DANFE (`pages/index.vue`): o SERVIDOR
 * compõe os bytes ESC/POS, esta camada só relaia ao agente do balcão. A
 * diferença é que o lote sai num trabalho só — os bytes já vêm concatenados,
 * com o corte parcial entre uma filipeta e a seguinte.
 *
 * ⚠️ **Não há queda para `window.print()` aqui, e é deliberado.** No recibo a
 * queda existe porque há um recibo DESENHADO na tela para o diálogo do
 * navegador imprimir. A filipeta não tem gêmea em HTML, e inventar uma criaria
 * um segundo leiaute com um segundo dono — exatamente o que a docstring do
 * `receipt_escpos` proíbe ("se cada máquina compusesse, dois balcões
 * imprimiriam diferente"). Então a falha é ALTA e explicada, nunca silenciosa:
 * o operador fica sabendo que esta estação não tem impressora e o que fazer.
 */
export interface TicketBatchResponse {
  ok: boolean;
  date_from: string;
  date_to: string;
  count: number;
  max_batch: number;
  orders: TicketRow[];
}

interface TicketPrintResponse {
  payload_b64: string;
  title: string;
  count?: number;
  reprint_count?: number;
}

export function usePosOrderTickets(pos: ComputedRef<POSProjection | null>) {
  const apiPath = usePosApiPath();
  const agent = useCounterAgent(pos);

  const today = isoDate(new Date());
  // A semana que vem é o padrão porque foi o exemplo do dono ("todos os pedidos
  // da semana"). O servidor tem o MESMO padrão — a tela não é a única a saber.
  const range = ref<TicketRange>(resolveRange("week", today));

  const query = computed(() => ({ date_from: range.value.date_from, date_to: range.value.date_to }));

  const { data, pending, error, refresh } = useFetch<TicketBatchResponse>(
    () => apiPath("/api/v1/backstage/orders/tickets/"),
    { query, credentials: "include", key: "pos-order-tickets" },
  );

  const rows = computed<TicketRow[]>(() => data.value?.orders ?? []);
  const count = computed(() => data.value?.count ?? 0);
  const maxBatch = computed(() => data.value?.max_batch ?? 0);
  const canPrint = computed(() => canPrintBatch(count.value, maxBatch.value));

  const printing = ref(false);
  const printingRef = ref("");

  function setPreset(preset: TicketPreset) {
    range.value = resolveRange(preset, today);
  }

  function setRange(next: Partial<TicketRange>) {
    range.value = { ...range.value, ...next };
  }

  /** A queda avisada: sem agente, dizer o que falta em vez de falhar mudo. */
  function warnNoAgent() {
    toast.error(
      `Esta estação não imprime: ${agent.unavailableReason.value} `
      + "As filipetas saem no balcão que tem impressora.",
    );
  }

  async function fetchPrintable(path: string, params?: Record<string, string>) {
    return await $fetch<TicketPrintResponse>(apiPath(path), {
      credentials: "include",
      query: params,
    });
  }

  /** O lote inteiro, em filipetas consecutivas. */
  async function printBatch(): Promise<boolean> {
    if (!import.meta.client || printing.value || !canPrint.value) return false;
    if (!agent.canKick.value) {
      warnNoAgent();
      return false;
    }
    printing.value = true;
    try {
      const job = await fetchPrintable("/api/v1/backstage/orders/tickets/escpos/", query.value);
      const outcome = await agent.print(job.payload_b64, job.title);
      if (outcome.status !== "printed") {
        toast.error(`As filipetas não saíram: ${outcome.detail || "o agente do balcão não respondeu"}.`);
        return false;
      }
      const reimpressas = job.reprint_count || 0;
      toast.success(
        `${job.count ?? count.value} filipetas na bobina.`
        + (reimpressas ? ` ${reimpressas} saíram marcadas como 2ª via.` : ""),
      );
      await refresh();
      return true;
    } catch (error) {
      toast.error(httpErrorMessage(error, "Falha ao compor as filipetas no servidor."));
      return false;
    } finally {
      printing.value = false;
    }
  }

  /** Uma filipeta só — a que caiu, a que rasgou, a que chegou agora. */
  async function printOne(ref: string): Promise<boolean> {
    if (!import.meta.client || printingRef.value) return false;
    if (!agent.canKick.value) {
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
        toast.error(`A filipeta de ${ref} não saiu: ${outcome.detail || "o agente do balcão não respondeu"}.`);
        return false;
      }
      toast.success(`Filipeta de ${ref} na bobina.`);
      await refresh();
      return true;
    } catch (error) {
      toast.error(httpErrorMessage(error, "Falha ao compor a filipeta no servidor."));
      return false;
    } finally {
      printingRef.value = "";
    }
  }

  return {
    today,
    range,
    rows,
    count,
    maxBatch,
    canPrint,
    pending,
    error,
    refresh,
    printing,
    printingRef,
    hasPrinter: agent.canKick,
    printerUnavailableReason: agent.unavailableReason,
    setPreset,
    setRange,
    printBatch,
    printOne,
  };
}
