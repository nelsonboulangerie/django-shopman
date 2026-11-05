// A caixa pessoal, leitura e escrita. Mora na layer porque o aviso é da PESSOA,
// não da tela: quem recebe precisa ver onde estiver.
//
// ADR-016 — o fetch REST é a FONTE DA VERDADE. O SSE só diz "chegou algo" e
// dispara o refetch; o poll fica como rede de segurança em cadência calma. Uma
// mensagem de push perdida custa, no pior caso, um ciclo de poll.
//
// UMA caixa por app (`useSharedLive`): o sino aparece no cabeçalho, na barra lateral,
// na barra compacta e no shell, e cada um abria o próprio SSE e o próprio poll. Eram
// três `/sse/notifications` por aba no PDV e leituras em pares no B.I. (beta 05/11).
import type {
  NotificationListResponse,
  SignInListResponse,
  UserNotification,
} from "../types/notification";
import { httpError, httpErrorMessage, isUnauthenticatedError } from "../utils/httpError";
import { useOperatorSession } from "./useOperatorSession";
import { useSharedLive } from "./useSharedLive";
import { coalesceRefresh } from "../utils/coalesceRefresh";
import type { OperatorSession } from "../types/operator";
import { unreadOf } from "../presentation/notifications";
import { updateAppBadge } from "../utils/appBadge";

/** Rede de segurança, não o motor: o SSE é quem avisa. 60s não pesa e não atrasa. */
const POLL_MS = 60_000;

export function useNotifications() {
  return useSharedLive("operator-inbox", createInbox, inbox => inbox.start());
}

function createInbox() {
  const operatorSession = useOperatorSession();
  const items = ref<UserNotification[]>([]);
  const unread = ref(0);
  const loading = ref(false);
  const error = ref("");
  const signInError = ref("");
  const signIns = ref<SignInListResponse["sign_ins"]>([]);
  const { data: session } = useNuxtData<OperatorSession>("operator-session");
  let generation = 0;
  const owner = () => session.value?.operator?.id ?? null;
  const current = (version: number) => version === generation;
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
    if (owner() == null) return;
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
    if (owner() == null) return;
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
    if (owner() == null) return;
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

  /**
   * "Marcar todas como lidas": as que estão na tela, e só elas. O servidor marca as
   * dele que ainda não foram vistas; o que chegou depois continua novo.
   */
  async function markAllRead(): Promise<void> {
    if (owner() == null) return;
    const version = generation;
    const ids = items.value.filter(item => !item.is_read).map(item => item.pk);
    if (!ids.length) return;
    try {
      await $fetch("/api/v1/backstage/notifications/v2/seen/", {
        method: "POST",
        body: { notification_ids: ids },
      });
    } catch {
      if (current(version)) error.value = "Não foi possível marcar os avisos como lidos. Tente novamente.";
      return;
    }
    if (current(version)) await refresh();
  }

  /**
   * "Não fui eu" sobre um acesso. Sem `confirm`, o servidor só descreve o que vai
   * acontecer (409 `needs_confirmation`); com ele, encerra as sessões da conta.
   * Devolve a descrição para a tela perguntar, ou `"done"`.
   */
  async function notMe(pk: number, confirm: boolean): Promise<{ needsConfirmation: string } | "done" | "failed"> {
    if (owner() == null) return "failed";
    const version = generation;
    try {
      await $fetch(`/api/v1/backstage/notifications/${pk}/action/`, {
        method: "POST",
        body: confirm ? { action: "not_me", confirm: true } : { action: "not_me" },
      });
    } catch (failure) {
      const { status, data } = httpError(failure);
      const detail = (data as { detail?: unknown } | null)?.detail;
      if (status === 409 && typeof detail === "string") return { needsConfirmation: detail };
      if (current(version)) {
        error.value = httpErrorMessage(failure, "Não foi possível encerrar os acessos. Tente novamente.");
      }
      return "failed";
    }
    if (current(version)) await refresh();
    return "done";
  }

  // O push (canal `user-<id>`) só chuta o refetch — quem manda é o fetch acima.
  const { realtime, start: startPush } = useUserNotifications(() => refresh());
  watch(unread, value => void updateAppBadge(value), { immediate: true });

  /** Liga o push e o poll (o primeiro sino montou); devolve como desligar. */
  function start(): () => void {
    void refresh();
    const timer = setInterval(refresh, POLL_MS);
    const stopPush = startPush();
    return () => {
      clearInterval(timer);
      stopPush();
    };
  }

  return {
    items,
    unread,
    loading,
    error,
    signInError,
    refresh,
    markRead,
    markAllRead,
    notMe,
    signIns,
    loadSignIns,
    realtime,
    start,
  };
}
