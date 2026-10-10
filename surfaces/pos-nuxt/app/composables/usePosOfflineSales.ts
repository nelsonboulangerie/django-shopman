import { createOfflineSaleQueue, type OfflineSaleQueue } from "~/utils/offlineSaleQueue";
import { deferredOfflineSaleStore, memoryOfflineSaleStore, openOfflineSaleStore } from "~/utils/offlineSaleStore";
import { offlineQueueAlert, type OfflineSale } from "~/presentation/offlineSales";

const CLOSE_SALE_PATH = "/api/v1/backstage/pos/sale/close/";
const FLUSH_LOCK = "shopman:pos:offline-sales-flush";
/** Com a conexão de pé e venda na fila, tenta de novo nesta cadência. */
const RETRY_EVERY_MS = 30_000;

let queue: OfflineSaleQueue | null = null;
let wired = false;

/**
 * A fila de vendas sem conexão do PDV, uma por aba (WP-PDV-SEM-CONEXAO).
 *
 * No cliente, abre o IndexedDB, carrega o que sobrou de antes (recarregou a tela,
 * reiniciou o dispositivo) e reenvia sozinha: ao voltar a conexão
 * (`useConnectivity().onReconnect`), ao abrir a tela e a cada 30 s enquanto houver
 * venda pendente. No servidor (SSR) a fila existe vazia, na memória, e não envia.
 */
export function usePosOfflineSales() {
  const action = usePosAction();
  const { isOnline, onReconnect } = useConnectivity();

  async function flushAndTell() {
    const report = await queue!.flush();
    if (report.sent.length) {
      const refs = report.sent.map((row) => row.orderRef).join(", ");
      useSonner.success(report.sent.length === 1
        ? `Venda guardada enviada: pedido ${refs}.`
        : `${report.sent.length} vendas guardadas enviadas: pedidos ${refs}.`);
      // A comanda mudou em outro dispositivo durante a queda: a venda entrou, e
      // o balcão fica sabendo o que seguiu aberto (o gerente recebe o detalhe).
      for (const row of report.sent) if (row.note) useSonner.info(row.note);
    }
    if (report.conflicts) {
      useSonner.error(report.conflicts === 1
        ? "1 venda guardada não entrou. Abra a lista para ver por quê."
        : `${report.conflicts} vendas guardadas não entraram. Abra a lista para ver por quê.`);
    }
    return report;
  }

  if (!queue) {
    const client = import.meta.client;
    queue = createOfflineSaleQueue({
      store: client
        ? deferredOfflineSaleStore(openOfflineSaleStore(), (store) => {
            if (queue) queue.state.durable = store.durable;
          })
        : memoryOfflineSaleStore(),
      send: (body) => action.call(CLOSE_SALE_PATH, { body }),
      readFailure: (error) => httpError(error),
      withLock: async (run) => {
        const locks = globalThis.navigator?.locks;
        if (!locks?.request) return run();
        return locks.request(FLUSH_LOCK, { ifAvailable: true }, async (lock) => (lock ? run() : null));
      },
    });
    if (client) {
      void queue.load().then(() => {
        if (globalThis.navigator?.onLine !== false && queue?.pending.value.length) void flushAndTell();
      });
    }
  }

  if (import.meta.client) {
    // Cada tela que usa a fila registra o próprio reconciliador (o registro morre
    // com a tela); rodadas simultâneas viram uma só pela guarda da fila.
    onReconnect(async () => { await flushAndTell(); });
  }
  if (import.meta.client && !wired) {
    wired = true;
    setInterval(() => {
      const current = queue;
      if (!current || current.state.sending || !current.pending.value.length) return;
      if (globalThis.navigator?.onLine === false) return;
      void flushAndTell();
    }, RETRY_EVERY_MS);
  }

  const current = queue;
  const pendingCount = computed(() => current.pending.value.length);
  const conflictCount = computed(() => current.conflicts.value.length);
  const alert = computed(() => offlineQueueAlert({
    online: isOnline.value !== false,
    pending: pendingCount.value,
    conflicts: conflictCount.value,
    sending: current.state.sending,
  }));

  return {
    isOnline,
    sales: computed(() => current.state.sales),
    sending: computed(() => current.state.sending),
    durable: computed(() => current.state.durable),
    /** Chave da venda guardada → pedido que o servidor devolveu ao enviá-la. */
    sentOrderRefs: computed(() => current.state.sentOrderRefs),
    pendingCount,
    conflictCount,
    /** Tudo que ainda não chegou ao servidor: é o que barra o fechamento do caixa. */
    unsentCount: computed(() => current.unsent.value),
    alert,
    enqueue: (sale: OfflineSale) => current.enqueue(sale),
    flush: flushAndTell,
    retry: async (id: string) => { await current.retry(id); },
    sendWithServerTotal: async (id: string) => { await current.sendWithServerTotal(id); },
  };
}
