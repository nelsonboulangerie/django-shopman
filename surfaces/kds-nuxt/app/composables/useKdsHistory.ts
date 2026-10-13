// Histórico de hoje da estação (dono, 13/10/2026): os pedidos concluídos e cancelados
// desde 0h, só desta estação. Leitura PRÓPRIA (`GET kds/<ref>/history/`), fora do quadro:
// o quadro vai a cada push e a cada 15 s, e o histórico só quando alguém abre. A busca
// é pelo código (ou pelo cliente) e alcança o dia inteiro; sem busca vêm os 100 mais
// recentes.
//
// Reabrir só existe onde o servidor deixa (`can_reopen`): o pedido que já saiu da cozinha
// só se vê, e a linha diz por quê. Reabrir devolve o ticket à fila em preparo.
import type { KDSHistoryProjection, KDSHistoryResponse } from "~/types/kds";

/** A busca espera a pessoa parar de digitar por isto antes de perguntar ao servidor. */
export const KDS_HISTORY_SEARCH_DEBOUNCE_MS = 250;

export function useKdsHistory(stationRef: string) {
  const open = ref(false);
  const query = ref("");
  const history = ref<KDSHistoryProjection | null>(null);
  const pending = ref(false);
  const error = ref<unknown>(null);
  const reopeningPk = ref<number | null>(null);

  // Ver o comentário do `postProxy` em useKdsBoard: path dinâmico contra o catch-all do
  // BFF estoura o typecheck do `$fetch` tipado; aqui ele é um cliente HTTP simples.
  const http = $fetch as (
    path: string,
    opts?: { method?: string; body?: Record<string, unknown>; query?: Record<string, string> },
  ) => Promise<unknown>;
  const path = `/api/v1/backstage/kds/${encodeURIComponent(stationRef)}/history/`;

  // Só a resposta da ÚLTIMA pergunta vale: a busca digitada depressa não pode ser
  // sobrescrita por uma resposta velha que chegou depois.
  let asked = 0;
  async function load() {
    const ticket = ++asked;
    pending.value = true;
    try {
      const q = query.value.trim();
      const response = (await http(path, q ? { query: { q } } : {})) as KDSHistoryResponse;
      if (ticket !== asked) return;
      history.value = response.history;
      error.value = null;
    } catch (err) {
      if (ticket === asked) error.value = err;
    } finally {
      if (ticket === asked) pending.value = false;
    }
  }

  watch(open, (value) => {
    if (value) void load();
    else query.value = "";
  });
  let searchTimer: ReturnType<typeof setTimeout> | null = null;
  watch(query, () => {
    if (!open.value) return;
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => void load(), KDS_HISTORY_SEARCH_DEBOUNCE_MS);
  });
  onBeforeUnmount(() => {
    if (searchTimer) clearTimeout(searchTimer);
  });

  /** Devolve o ticket à fila (a mesma porta do Reabrir de sempre). True quando voltou. */
  async function reopen(pk: number): Promise<boolean> {
    if (reopeningPk.value != null) return false;
    reopeningPk.value = pk;
    try {
      await http(`/api/v1/backstage/kds/tickets/${pk}/recall/`, { method: "POST", body: {} });
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não deu para reabrir o pedido. Tente de novo."));
      await load();
      return false;
    } finally {
      reopeningPk.value = null;
    }
  }

  return { open, query, history, pending, error, reopeningPk, load, reopen };
}
