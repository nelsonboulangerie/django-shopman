import type { MoneyRead } from "~/presentation/orderReason";
import type {
  OperatorOrderProjection,
  OrderDetailResponse,
} from "~/types/orders";

/**
 * A leitura do pedido para o diálogo de recusa do painel (WP-G06).
 *
 * O cartão do painel não diz o que a recusa faz com o dinheiro, e não vai dizer: o
 * fato mora no detalhe do pedido (`cancel_money_effect`). O diálogo lê o detalhe ao
 * abrir, e cada abertura lê de novo (o pagamento pode ter caído entre uma e outra).
 * A leitura é a mesma `GET orders/<ref>/` da página do pedido: não grava nada nem
 * pergunta ao gateway.
 *
 * A resposta que chega depois de o diálogo fechar, ou de outro pedido abrir, é
 * descartada: a leitura mais nova vence.
 */
export function useOrderReasonRead() {
  const order = shallowRef<OperatorOrderProjection | null>(null);
  const state = ref<MoneyRead>("ready");
  let latest = 0;

  async function read(ref_: string): Promise<void> {
    const mine = ++latest;
    order.value = null;
    state.value = "loading";
    try {
      const response = await $fetch<OrderDetailResponse>(
        `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/`,
      );
      if (mine !== latest) return;
      order.value = response.order;
      state.value = "ready";
    } catch {
      if (mine !== latest) return;
      order.value = null;
      state.value = "error";
    }
  }

  function clear() {
    latest += 1;
    order.value = null;
    state.value = "ready";
  }

  return { order, state, read, clear };
}
