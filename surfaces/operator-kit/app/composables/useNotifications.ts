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
import { unreadOf } from "../presentation/notifications";

/** Rede de segurança, não o motor: o SSE é quem avisa. 60s não pesa e não atrasa. */
const POLL_MS = 60_000;

export function useNotifications() {
  const items = ref<UserNotification[]>([]);
  const unread = ref(0);
  const loading = ref(false);

  async function refresh(): Promise<void> {
    loading.value = true;
    try {
      const res = await $fetch<NotificationListResponse>(
        "/api/v1/backstage/notifications/",
        { query: { all: 1, limit: 30 } },
      );
      items.value = res.notifications ?? [];
      unread.value = unreadOf(res);
    } catch {
      // Silêncio proposital: a caixa é acessório da tela, e um erro de rede aqui
      // não pode virar um toast por cima de quem está atendendo.
      items.value = [];
      unread.value = 0;
    } finally {
      loading.value = false;
    }
  }

  async function markRead(pk: number): Promise<void> {
    try {
      await $fetch(`/api/v1/backstage/notifications/${pk}/read/`, {
        method: "POST",
        body: {},
      });
    } catch {
      // best-effort; o refetch reconcilia.
    }
    await refresh();
  }

  const signIns = ref<SignInListResponse["sign_ins"]>([]);
  async function loadSignIns(): Promise<void> {
    try {
      const res = await $fetch<SignInListResponse>("/api/v1/backstage/sign-ins/", {
        query: { limit: 30 },
      });
      signIns.value = res.sign_ins ?? [];
    } catch {
      signIns.value = [];
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
    if (timer) clearInterval(timer);
    timer = null;
  });

  return { items, unread, loading, refresh, markRead, signIns, loadSignIns, realtime };
}
