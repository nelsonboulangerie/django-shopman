// A caixa pessoal, leitura e escrita. Mora na layer porque o aviso é da PESSOA,
// não da tela: quem recebe precisa ver onde estiver.
//
// ADR-016 — o fetch REST é a FONTE DA VERDADE. O SSE só diz "chegou algo" e
// dispara o refetch; o poll fica como rede de segurança em cadência calma. Uma
// mensagem de push perdida custa, no pior caso, um ciclo de poll.
import type {
  NotificationListResponse,
  SignInListResponse,
  UserNotification,
} from "../types/notification";
import { httpError, httpErrorMessage, isUnauthenticatedError } from "../utils/httpError";
import { useOperatorSession } from "./useOperatorSession";
import { coalesceRefresh } from "../utils/coalesceRefresh";
import type { OperatorSession } from "../types/operator";
import { unreadOf } from "../presentation/notifications";

/** Rede de segurança, não o motor: o SSE é quem avisa. 60s não pesa e não atrasa. */
const POLL_MS = 60_000;

export function useNotifications() {
  const operatorSession = useOperatorSession();
  const items = ref<UserNotification[]>([]);
  const unread = ref(0);
  const loading = ref(false);
  const error = ref("");
  const signInError = ref("");
  const signIns = ref<SignInListResponse["sign_ins"]>([]);
  const { data: session } = useNuxtData<OperatorSession>("operator-session");
  let generation = 0;
  let disposed = false;
  const owner = () => session.value?.operator?.id ?? null;
  const current = (version: number) => !disposed && version === generation;
  watch(owner, () => {
    generation++;
    items.value = [];
    unread.value = 0;
    signIns.value = [];
    error.value = "";
    signInError.value = "";
    if (owner() != null) void refresh();
  }, { flush: "sync" });

  const refresh = coalesceRefresh(async () => {
    if (owner() == null || disposed) return;
    const version = generation;
    loading.value = true;
    try {
      const res = await $fetch<NotificationListResponse>(
        "/api/v1/backstage/notifications/",
        { query: { all: 1, limit: 30 } },
      );
      if (!current(version)) return;
      error.value = "";
      items.value = res.notifications ?? [];
      unread.value = unreadOf(res);
    } catch (failure) {
      if (!current(version)) return;
      if (isUnauthenticatedError(failure)) {
        items.value = [];
        unread.value = 0;
        signIns.value = [];
        operatorSession.flagIfUnauthenticated(failure);
        error.value = "Identifique-se novamente para consultar seus avisos.";
      } else if (httpError(failure).status === 403) {
        error.value = httpErrorMessage(failure, "Esta sessão não tem permissão para consultar os avisos.");
      } else {
        error.value = "Não foi possível atualizar os avisos. A última leitura pode estar desatualizada.";
      }
    } finally {
      loading.value = false;
    }
  });

  async function markRead(pk: number): Promise<void> {
    if (owner() == null || disposed) return;
    const version = generation;
    try {
      await $fetch(`/api/v1/backstage/notifications/${pk}/read/`, {
        method: "POST",
        body: {},
      });
    } catch {
      if (current(version)) error.value = "Não foi possível confirmar a leitura do aviso. Tente novamente.";
      return;
    }
    if (current(version)) await refresh();
  }

  async function loadSignIns(): Promise<void> {
    if (owner() == null || disposed) return;
    const version = generation;
    try {
      const res = await $fetch<SignInListResponse>("/api/v1/backstage/sign-ins/", {
        query: { limit: 30 },
      });
      if (!current(version)) return;
      signInError.value = "";
      signIns.value = res.sign_ins ?? [];
    } catch {
      if (current(version)) signInError.value = "Não foi possível atualizar os acessos. Tente novamente.";
    }
  }

  // O push (canal `user-<id>`) só chuta o refetch — quem manda é o fetch acima.
  const { realtime } = useUserNotifications(() => refresh());

  let timer: ReturnType<typeof setInterval> | null = null;
  onMounted(() => {
    refresh();
    timer = setInterval(refresh, POLL_MS);
  });
  onBeforeUnmount(() => {
    disposed = true;
    generation++;
    if (timer) clearInterval(timer);
    timer = null;
  });

  return { items, unread, loading, error, signInError, refresh, markRead, signIns, loadSignIns, realtime };
}
