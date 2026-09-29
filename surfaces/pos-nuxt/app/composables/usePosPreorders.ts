import type { Ref } from "vue";

import type { TicketRange } from "~/presentation/orderTickets";
import { railAriaLabel, railBadge } from "~/presentation/preorders";
import type { PreorderDetailResponse, PreorderListResponse } from "~/types/preorders";

/** A leitura da semana que começa hoje — a resposta padrão da rota. Uma chave só,
 *  dividida pela barra lateral (o selo) e pela casa das Encomendas (os totais). */
const AHEAD_KEY = "pos-preorders-ahead";

/**
 * As leituras que o evento de pedido refaz: a semana à frente, Hoje e Semana. A
 * busca fica de fora — ela só pergunta com o que procurar, e um refresh cego a
 * faria pedir o intervalo inteiro sem filtro.
 */
export const PREORDERS_LIVE_KEYS = [AHEAD_KEY, "pos-preorders-today", "pos-preorders-week"];

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

/** A semana que começa hoje (hoje + 6), sem busca: o selo da barra e a casa. */
export function usePosPreordersAhead() {
  const apiPath = useApiPath();
  const { data, pending, error, refresh } = useFetch<PreorderListResponse>(
    () => apiPath("/api/v1/backstage/pos/preorders/"),
    { key: AHEAD_KEY, credentials: "include", server: false, lazy: true },
  );
  return { list: data, pending, error, refresh };
}

function isDenied(error: unknown): boolean {
  const status = (error as { statusCode?: number } | null)?.statusCode;
  return status === 401 || status === 403;
}

/**
 * O item "Encomendas" da barra lateral: se aparece, e o selo.
 *
 * - **Permissão por sondagem**: a rota exige `shop.manage_orders`; 401/403 = o item
 *   some (a tela não oferece porta que vai bater na cara). A resposta boa fica
 *   lembrada em `useState`, para o item não piscar a cada troca de tela.
 * - **SSE primeiro** (ADR-016): o canal dos pedidos (`/sse/orders`, o mesmo do
 *   Gestor) avisa que um pedido nasceu, mudou ou foi pago, e o aviso refaz as
 *   leituras canônicas das Encomendas que estão na tela (`PREORDERS_LIVE_KEYS`).
 *   Sem stream de pé, o fallback é calmo: a cada 2 minutos, e ao voltar à aba.
 */
export function usePosPreordersRail() {
  const { list, error, refresh } = usePosPreordersAhead();
  const allowed = useState<boolean>("pos-preorders-allowed", () => false);

  watch(list, (value) => { if (value) allowed.value = true; }, { immediate: true });
  watch(error, (value) => { if (isDenied(value)) allowed.value = false; }, { immediate: true });

  usePosEvents(
    () => {
      if (allowed.value) void refreshNuxtData(PREORDERS_LIVE_KEYS);
      // Sem resposta boa ainda (rede caiu na primeira leitura): tenta de novo no
      // tick calmo. Recusa de permissão não se repete.
      else if (!isDenied(error.value)) void refresh();
    },
    { channels: POS_ORDER_CHANNELS, pollMs: 120_000, enabled: () => allowed.value },
  );

  const badge = computed(() => railBadge(list.value));
  return { allowed, badge, ariaLabel: computed(() => railAriaLabel(badge.value)) };
}
