import { computed, reactive } from "vue";

import { classifyOfflineSend, type OfflineSale } from "~/presentation/offlineSales";
import type { OfflineSaleStore } from "~/utils/offlineSaleStore";

/** Uma rodada de envio: quantas entraram, quantas o servidor recusou, por que parou. */
export interface OfflineFlushReport {
  sent: Array<{ id: string; orderRef: string; note?: string }>;
  conflicts: number;
  stopped: "" | "network" | "server" | "session" | "busy";
}

export interface OfflineSaleQueueDeps {
  store: OfflineSaleStore;
  /** Manda o corpo ao `close_sale`. Falha com o erro do `$fetch` (status/data). */
  send: (body: Record<string, unknown>) => Promise<unknown>;
  /** Lê status/data de uma falha (o `httpError` do kit). */
  readFailure: (error: unknown) => { status: number; data?: unknown };
  /**
   * Trava entre abas: duas janelas do PDV não reenviam a mesma fila ao mesmo
   * tempo. O servidor aguentaria (mesma chave, mesmo pedido), mas a tela de uma
   * diria "enviando" sobre uma venda que a outra já levou.
   */
  withLock?: <T>(run: () => Promise<T>) => Promise<T | null>;
}

/**
 * A fila de vendas sem conexão: guarda, reenvia em ordem e diz o que ficou.
 *
 * A ordem é a da cobrança (`capturedAt`). Uma falha de REDE para a rodada
 * inteira (não adianta tentar a próxima); uma RECUSA do servidor marca só
 * aquela venda e a rodada segue, porque cada venda é independente das outras.
 * Venda enviada sai da fila; recusada fica, com o motivo, até alguém resolver.
 */
export function createOfflineSaleQueue(deps: OfflineSaleQueueDeps) {
  const state = reactive({
    sales: [] as OfflineSale[],
    sending: false,
    loaded: false,
    durable: deps.store.durable,
    /** As enviadas nesta aba: chave da venda → pedido que o servidor devolveu. */
    sentOrderRefs: {} as Record<string, string>,
  });

  const pending = computed(() => state.sales.filter((sale) => sale.status === "pending"));
  const conflicts = computed(() => state.sales.filter((sale) => sale.status === "conflict"));
  /** Tudo que ainda não chegou ao servidor (o que barra o fechamento do caixa). */
  const unsent = computed(() => state.sales.length);

  function sorted(rows: OfflineSale[]): OfflineSale[] {
    return [...rows].sort((a, b) => a.capturedAt.localeCompare(b.capturedAt));
  }

  async function load(): Promise<void> {
    state.sales = sorted(await deps.store.list());
    state.loaded = true;
  }

  async function save(sale: OfflineSale): Promise<void> {
    await deps.store.put(sale);
    const others = state.sales.filter((row) => row.id !== sale.id);
    state.sales = sorted([...others, sale]);
  }

  /** Guarda a venda. Só resolve depois que ela está no armazenamento. */
  async function enqueue(sale: OfflineSale): Promise<void> {
    await save({ ...sale, status: "pending", attempts: 0 });
  }

  async function runFlush(): Promise<OfflineFlushReport> {
    const report: OfflineFlushReport = { sent: [], conflicts: 0, stopped: "" };
    state.sending = true;
    try {
      // Relê do armazenamento: outra aba pode ter enviado ou guardado algo.
      await load();
      for (const sale of pending.value) {
        let outcome;
        try {
          outcome = classifyOfflineSend({ response: await deps.send(sale.body) });
        } catch (error) {
          outcome = classifyOfflineSend({ failure: deps.readFailure(error) });
        }
        if (outcome.kind === "sent") {
          await deps.store.remove(sale.id);
          state.sales = state.sales.filter((row) => row.id !== sale.id);
          report.sent.push(outcome.note
            ? { id: sale.id, orderRef: outcome.orderRef, note: outcome.note }
            : { id: sale.id, orderRef: outcome.orderRef });
          state.sentOrderRefs = { ...state.sentOrderRefs, [sale.id]: outcome.orderRef };
          continue;
        }
        if (outcome.kind === "conflict") {
          await save({ ...sale, status: "conflict", attempts: sale.attempts + 1, lastError: outcome.error });
          report.conflicts += 1;
          continue;
        }
        await save({ ...sale, attempts: sale.attempts + 1 });
        report.stopped = outcome.reason;
        break;
      }
    } finally {
      state.sending = false;
    }
    return report;
  }

  /** Reenvia o que está pendente. Uma rodada por vez (nesta aba e entre abas). */
  async function flush(): Promise<OfflineFlushReport> {
    if (state.sending) return { sent: [], conflicts: 0, stopped: "busy" };
    if (!deps.withLock) return runFlush();
    const report = await deps.withLock(runFlush);
    return report ?? { sent: [], conflicts: 0, stopped: "busy" };
  }

  /** A recusa foi resolvida fora (ex.: caixa aberto de novo): volta para a fila. */
  async function retry(id: string): Promise<OfflineFlushReport> {
    const sale = state.sales.find((row) => row.id === id);
    if (sale) await save({ ...sale, status: "pending", lastError: undefined });
    return flush();
  }

  /**
   * `total_changed`: o operador aceita o total que o servidor calculou. A venda
   * vai com esse total; a diferença para o que entrou na gaveta aparece no
   * fechamento do caixa, que é onde dinheiro a mais ou a menos se explica.
   */
  async function sendWithServerTotal(id: string): Promise<OfflineFlushReport> {
    const sale = state.sales.find((row) => row.id === id);
    const newTotalQ = sale?.lastError?.newTotalQ;
    if (!sale || typeof newTotalQ !== "number") return flush();
    await save({
      ...sale,
      status: "pending",
      totalQ: newTotalQ,
      body: { ...sale.body, expected_total_q: newTotalQ },
      lastError: undefined,
    });
    return flush();
  }

  return { state, pending, conflicts, unsent, load, enqueue, flush, retry, sendWithServerTotal };
}

export type OfflineSaleQueue = ReturnType<typeof createOfflineSaleQueue>;
