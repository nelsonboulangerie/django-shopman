import { useOperatorResourceKey } from "./useOperatorResourceKey";
// A loja no iFood — o que o iFood diz da loja (última conferência) e se ele diverge
// da casa. O fetch REST é a fonte da verdade, relido com calma a cada minuto: a
// conferência do maintenance-worker roda a cada poucos minutos. Ligar e desligar o
// iFood é o toggle "Ativo" do card do canal, comum a todo canal.
import type { IFoodStoreProjection } from "~/types/ifoodStore";

const POLL_MS = 60_000;

export function useIFoodStore() {
  const { data, refresh } = useFetch<IFoodStoreProjection>("/api/v1/backstage/ifood/store/", {
    key: useOperatorResourceKey("ifood-store"),
    server: false,
  });
  const store = computed<IFoodStoreProjection | null>(() => data.value ?? null);

  let timer: ReturnType<typeof setInterval> | null = null;
  onMounted(() => {
    timer = setInterval(() => { void refresh(); }, POLL_MS);
  });
  onBeforeUnmount(() => {
    if (timer) clearInterval(timer);
    timer = null;
  });

  return { store, refresh };
}
