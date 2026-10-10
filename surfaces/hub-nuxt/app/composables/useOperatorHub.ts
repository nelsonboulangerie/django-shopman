import { QUEUE_POLL_MS } from "~/presentation/hub";
import type { HubQueueProjection, HubResponse, HubTileProjection, OperatorHubProjection } from "~/types/hub";

/**
 * Read-side da Central: um único fetch da projection do hub (`{ hub }`) + as fatias que a
 * tela consome (tiles, fila "Precisa de você" e nome do operador). SSR pronta (reload cai
 * na tela certa); erro (401) sobe o gate de login na shell.
 *
 * Tempo real: a Central ainda não tem canal SSE próprio (a fila soma cinco apps, cada um
 * com o seu canal e a sua permissão). Até ter, ela relê a fila num poll calmo, só com a
 * tela visível, e na hora em que a tela volta a aparecer (ADR-016: o fetch canônico é a
 * verdade; o poll é o fallback).
 */
export async function useOperatorHub() {
  const apiPath = useApiPath();
  const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;

  // ⚠️ Os ganchos de ciclo de vida vêm ANTES do `await`: depois dele não há instância
  // ativa, o Vue descarta o `onMounted` com um aviso, e o poll nunca começava (a tela
  // dizia "Atualiza sozinho a cada 30 s" e não atualizava).
  let reload: () => Promise<unknown> = async () => undefined;
  let busy = () => false;
  let timer: ReturnType<typeof setInterval> | null = null;
  const visible = () => typeof document === "undefined" || document.visibilityState === "visible";
  const tick = () => {
    if (visible() && !busy()) void reload();
  };
  const onVisibility = () => {
    if (visible()) void reload();
  };

  onMounted(() => {
    timer = setInterval(tick, QUEUE_POLL_MS);
    document.addEventListener("visibilitychange", onVisibility);
  });
  onBeforeUnmount(() => {
    if (timer) clearInterval(timer);
    timer = null;
    document.removeEventListener("visibilitychange", onVisibility);
  });

  const { data, pending, error, refresh } = await useFetch<HubResponse>(
    () => apiPath("/api/v1/backstage/hub/"),
    { credentials: "include", headers: requestHeaders },
  );
  reload = () => refresh();
  busy = () => pending.value;

  // A última leitura boa fica: a releitura que falha zera o `data` do `useFetch`, e a
  // tela que já mostrava a fila viraria a tela de erro inteira. Com a última leitura, a
  // fila segue na tela e o cabeçalho avisa de quando ela é.
  const lastHub = shallowRef<OperatorHubProjection | null>(data.value?.hub ?? null);
  watch(
    () => data.value?.hub,
    (value) => {
      if (value) lastHub.value = value;
    },
  );
  const hub = computed<OperatorHubProjection | null>(() => data.value?.hub ?? lastHub.value);
  const tiles = computed<HubTileProjection[]>(() => hub.value?.tiles ?? []);
  const queue = computed<HubQueueProjection | null>(() => hub.value?.queue ?? null);
  const operatorName = computed(() => hub.value?.operator_name ?? "");
  const shopName = computed(() => hub.value?.shop_name ?? "");

  return { data, hub, tiles, queue, operatorName, shopName, pending, error, refresh };
}
