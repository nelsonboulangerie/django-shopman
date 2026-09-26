import type { Ref } from "vue";

import type { TicketRange } from "~/presentation/orderTickets";
import type { PreorderDetailResponse, PreorderListResponse } from "~/types/preorders";

/**
 * A leitura das Encomendas: um intervalo (e uma busca) → a lista por dia.
 *
 * O corte, o saldo e a situação são do servidor
 * (`backstage/projections/preorders.py`); esta camada só pede o intervalo que a
 * tela escolheu e expõe a resposta. Leitura client-side (`server: false`): a
 * permissão é do operador identificado na estação, e o SSR não tem quem seja.
 *
 * `enabled` segura a requisição — a busca não pergunta nada ao servidor antes
 * de haver o que procurar. Com `enabled` falso a lista volta vazia, nunca a
 * resposta da busca anterior.
 */
export function usePosPreorders(options: {
  key: string;
  range: Ref<TicketRange>;
  query?: Ref<string>;
  enabled?: Ref<boolean>;
}) {
  const apiPath = useApiPath();
  const params = computed(() => ({
    date_from: options.range.value.date_from,
    date_to: options.range.value.date_to,
    ...(options.query?.value.trim() ? { q: options.query.value.trim() } : {}),
  }));
  const enabled = computed(() => options.enabled?.value ?? true);

  const { data, pending, error, refresh } = useFetch<PreorderListResponse>(
    () => apiPath("/api/v1/backstage/pos/preorders/"),
    {
      key: options.key,
      query: params,
      credentials: "include",
      server: false,
      lazy: true,
      immediate: enabled.value,
      watch: false,
    },
  );

  // Um watcher só, que respeita o `enabled`: o `watch` embutido do useFetch
  // perguntaria ao servidor a cada letra, inclusive antes do mínimo da busca.
  watch([params, enabled], () => {
    if (enabled.value) void refresh();
  }, { deep: true });

  const list = computed(() => (enabled.value ? data.value : null));
  const days = computed(() => list.value?.days ?? []);

  return {
    list,
    days,
    count: computed(() => list.value?.count ?? 0),
    totalDisplay: computed(() => list.value?.total_display ?? ""),
    today: computed(() => list.value?.today ?? ""),
    pending,
    error,
    refresh,
  };
}

/** Uma encomenda, para o detalhe. 404 = não é encomenda (ou não existe). */
export function usePosPreorderDetail(ref: Ref<string>) {
  const apiPath = useApiPath();
  const { data, pending, error, refresh } = useFetch<PreorderDetailResponse>(
    () => apiPath(`/api/v1/backstage/pos/preorders/${encodeURIComponent(ref.value)}/`),
    { key: `pos-preorder:${ref.value}`, credentials: "include", server: false, lazy: true },
  );
  return { detail: data, pending, error, refresh };
}
