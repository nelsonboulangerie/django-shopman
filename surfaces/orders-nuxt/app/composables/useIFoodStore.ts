import { useOperatorResourceKey } from "./useOperatorResourceKey";
// A loja no iFood (menu de mais opções do Gestor). O fetch REST é a fonte da verdade;
// enquanto uma pausa está sendo pedida ou retomada, a tela reconsulta a cada poucos
// segundos até a Directive responder — fora disso, uma leitura calma por minuto.
import type { IFoodStoreProjection } from "~/types/ifoodStore";
import { pauseInFlight } from "~/presentation/ifoodStore";

const IN_FLIGHT_POLL_MS = 3_000;
const IDLE_POLL_MS = 60_000;

export function useIFoodStore() {
  const { data, refresh } = useFetch<IFoodStoreProjection>("/api/v1/backstage/ifood/store/", {
    key: useOperatorResourceKey("ifood-store"),
    server: false,
  });
  const store = computed<IFoodStoreProjection | null>(() => data.value ?? null);
  const busy = ref(false);

  let timer: ReturnType<typeof setTimeout> | null = null;
  let mounted = false;
  function schedule() {
    if (timer) clearTimeout(timer);
    if (!mounted) return;
    timer = setTimeout(async () => {
      await refresh();
      schedule();
    }, pauseInFlight(store.value) ? IN_FLIGHT_POLL_MS : IDLE_POLL_MS);
  }
  onMounted(() => {
    mounted = true;
    schedule();
  });
  onBeforeUnmount(() => {
    mounted = false;
    if (timer) clearTimeout(timer);
    timer = null;
  });

  async function send(path: string, body: Record<string, unknown>, fallback: string): Promise<boolean> {
    if (busy.value) return false;
    busy.value = true;
    try {
      data.value = await $fetch<IFoodStoreProjection>(path, { method: "POST", body });
      schedule();
      return true;
    } catch (error) {
      useSonner.error(httpErrorMessage(error, fallback));
      await refresh();
      return false;
    } finally {
      busy.value = false;
    }
  }

  function pause(duration: string, reason: string): Promise<boolean> {
    return send("/api/v1/backstage/ifood/store/pause/", { duration, reason }, "Não foi possível pausar o iFood.");
  }

  function resume(): Promise<boolean> {
    return send("/api/v1/backstage/ifood/store/resume/", {}, "Não foi possível retomar o iFood.");
  }

  return { store, busy, refresh, pause, resume };
}
