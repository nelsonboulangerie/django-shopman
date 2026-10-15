import type { PublicStatusSnapshot } from "~/types/status";
import { safeSnapshot } from "~/utils/statusPresentation";

const FALLBACK: PublicStatusSnapshot = {
  schemaVersion: 1,
  overall: "unknown",
  observedAt: null,
  components: [
    { id: "online_store", label: "Loja online", description: "Cardápio, carrinho e acompanhamento de pedidos.", status: "unknown" },
    { id: "service_operations", label: "Atendimento e operações", description: "Capacidades que sustentam o atendimento nas lojas.", status: "unknown" },
  ],
};

export function usePublicStatus() {
  const snapshot = ref<PublicStatusSnapshot>(FALLBACK);
  const loading = ref(true);
  const refreshing = ref(false);

  const refresh = async () => {
    refreshing.value = !loading.value;
    try {
      const response = await $fetch<PublicStatusSnapshot>("/api/status", {
        retry: 0,
        timeout: 6_000,
      });
      snapshot.value = safeSnapshot(response);
    } catch {
      try {
        const fallback = await $fetch<PublicStatusSnapshot>("/status.snapshot.json", { retry: 0 });
        snapshot.value = safeSnapshot(fallback);
      } catch {
        snapshot.value = FALLBACK;
      }
    } finally {
      loading.value = false;
      refreshing.value = false;
    }
  };

  let timer: ReturnType<typeof setInterval> | undefined;
  onMounted(() => {
    void refresh();
    timer = setInterval(() => void refresh(), 60_000);
  });
  onBeforeUnmount(() => timer && clearInterval(timer));

  return { snapshot: readonly(snapshot), loading: readonly(loading), refreshing: readonly(refreshing), refresh };
}
