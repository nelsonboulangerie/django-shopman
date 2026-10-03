import { useOperatorResourceKey } from "./useOperatorResourceKey";
import { useReadMetadata } from "./useReadMetadata";
import { historyApiQuery, type HistoryQuery } from "~/presentation/history";
import type { OrderHistoryResponse } from "~/types/history";

// Histórico do Gestor: pedidos fechados, filtrados e paginados NO SERVIDOR
// (/api/v1/backstage/orders/history/). Permissão: `shop.manage_orders`, a mesma do quadro.
const URL = "/api/v1/backstage/orders/history/";

export function useOrderHistory(query: Ref<HistoryQuery>, today: Ref<string>) {
  const { data, pending, error, refresh } = useFetch<OrderHistoryResponse>(URL, {
    key: useOperatorResourceKey("orders:history"),
    query: computed(() => historyApiQuery(query.value, today.value)),
    dedupe: "defer",
    onResponseError: operatorSessionOnError,
  });
  const readMetadata = useReadMetadata(data, error);
  // A última página confirmada fica na tela enquanto a próxima carrega: trocar de
  // filtro não pisca a lista inteira para o esqueleto.
  const lastConfirmed = shallowRef(data.value?.history ?? null);
  watch(data, (value) => { if (value?.history) lastConfirmed.value = value.history; }, { flush: "sync" });
  const history = computed(() => data.value?.history ?? lastConfirmed.value);
  return { history, pending, error, refresh, readMetadata };
}
