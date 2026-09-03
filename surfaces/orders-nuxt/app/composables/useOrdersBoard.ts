// Order board read-side. Single source for the live queue:
//   - useFetch the canonical two-zone projection (GET /api/v1/backstage/orders/);
//   - poll every 30s as a robust fallback (mirrors the Admin queue `every 30s`);
//   - SSE realtime: EventSource same-origin no BFF (/sse/orders → proxy do
//     /events/orders/ do Django) → refresh on push.
// Writes go through the django proxy (CSRF handled there) and reconcile via refresh.
// SSE/poll are client-only (EventSource is a browser API).
import type { CancellationReason, OrderQueueResponse, TwoZoneQueueProjection } from "~/types/orders";
import { newOrderPush, preorderGroups, zonesView, type PreorderGroup, type ZoneView } from "~/presentation/board";

export type { CancellationReason };

export function useOrdersBoard() {
  const config = useRuntimeConfig();
  const path = "/api/v1/backstage/orders/";

  // Antes do destravamento por PIN toda leitura volta 403 `station_locked`, e o
  // board desenhava "Falha ao carregar a fila. Reconectando…" — a tela mandava
  // o operador chamar suporte de rede na abertura de todo turno, para um estado
  // que é só "você ainda não se identificou". O PDV já erguia esta bandeira na
  // leitura (`usePosTerminal`); o Gestor não erguia em lugar nenhum, e por isso
  // o `locked` do kit nunca sabia o que o servidor acabou de dizer.
  const { flagIfStationLocked } = useStationLock();

  // useFetch (not useAsyncData) so the SSR payload transfers reliably (POS gotcha).
  const { data, pending, error, refresh } = useFetch<OrderQueueResponse>(path, {
    key: "orders-queue",
    server: true,
    // Sessão expirou no meio do turno → o poll passa a 401/403. Reabre o gate de
    // operador (re-fetch da sessão) em vez de deixar "reconectando…" para sempre.
    onResponseError: operatorSessionOnError,
  });

  watch(error, (value) => { if (value) flagIfStationLocked(value); }, { immediate: true });

  const queue = computed<TwoZoneQueueProjection | null>(() => data.value?.queue ?? null);
  const zones = computed<ZoneView[]>(() => (queue.value ? zonesView(queue.value) : []));
  const totalCount = computed(() => queue.value?.total_count ?? 0);
  // Encomendas confirmadas para datas futuras, agrupadas pela data combinada.
  const preorders = computed<PreorderGroup[]>(() => (queue.value ? preorderGroups(queue.value) : []));
  // Aparelhos na rua (maquininha): o quadro responde "onde está" sem abrir card.
  const equipmentOut = computed(() => queue.value?.equipment_out ?? []);

  // Realtime + polling (client only). `realtime` diz honestamente ao operador se o board
  // recebe pushes ao vivo (SSE aberto) ou caiu no poll de 30s — a bolinha "ao vivo" só
  // acende quando genuinamente vivo ([[feedback_transparent_timeouts]], [[feedback_no_overpromise_tracking]]).
  const realtime = ref<"connecting" | "live" | "polling">("polling");
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: EventSource | null = null;

  // ── pedido novo: som (mutável) + aviso mesmo com a aba oculta ─────────────
  // O beep/mute é o do kit (mesmo do KDS), com chave própria do Gestor. O push
  // SSE de `kind === "created"` dispara o aviso; mudança de status não grita.
  //
  // Aqui o aviso INSISTE (`startAlert`), diferente do KDS: no KDS o operador
  // está de frente para a tela; no Gestor o pedido chega enquanto a loja toca
  // a vida dela, e um toque único já deixou passar pedido de cliente real.
  // O kit para de repetir no primeiro toque/tecla — presença cala o aviso.
  const {
    soundOn,
    soundBlocked,
    toggleSound: toggleAlertSound,
    startAlert,
  } = useAlertSound("gestor_sound");

  function toggleSound() {
    toggleAlertSound();
    // Mesmo gesto que destrava o autoplay pede a permissão de notificação: fora
    // de um gesto do usuário o browser ignora (ou penaliza) o pedido.
    if (
      soundOn.value &&
      import.meta.client &&
      "Notification" in window &&
      Notification.permission === "default"
    ) {
      Notification.requestPermission().catch(() => {});
    }
  }

  // Título piscando enquanto a aba está oculta — restaurado ao voltar (o
  // listener de visibilitychange abaixo chama stopTitleAlert).
  let titleTimer: ReturnType<typeof setInterval> | null = null;
  let baseTitle = "";
  function stopTitleAlert() {
    if (!titleTimer) return;
    clearInterval(titleTimer);
    titleTimer = null;
    document.title = baseTitle;
  }
  function startTitleAlert(ref_: string) {
    if (titleTimer) return;
    baseTitle = document.title;
    let flip = false;
    titleTimer = setInterval(() => {
      flip = !flip;
      document.title = flip ? `● Pedido novo${ref_ ? ` ${ref_}` : ""}` : baseTitle;
    }, 1_500);
  }

  function notifyNewOrder(ref_: string) {
    // Silenciosamente degradável: sem API ou sem permissão, som e título cobrem.
    try {
      if (!("Notification" in window) || Notification.permission !== "granted") return;
      const n = new Notification(`Pedido novo${ref_ ? ` ${ref_}` : ""}`, {
        body: "Chegou um pedido novo no quadro.",
        tag: "gestor-new-order",
      });
      n.onclick = () => { window.focus(); n.close(); };
    } catch {
      // construtor pode lançar (ex.: Android sem service worker) — sem drama
    }
  }

  function announceNewOrder(ref_: string) {
    startAlert();
    if (document.visibilityState !== "visible") {
      notifyNewOrder(ref_);
      startTitleAlert(ref_);
    }
  }

  function connectSse() {
    if (source) return;
    // Same-origin sempre: o BFF (server/routes/sse/orders.ts) faz streaming do
    // eventstream do Django, em dev e em prod — nada de gate por origem.
    const url = ssePath("/sse/orders", config.app.baseURL);
    try {
      realtime.value = "connecting";
      source = new EventSource(url, { withCredentials: true });
      // Todo push refaz o fetch canônico; só o de pedido NOVO também avisa.
      const onPush = (ev: Event) => {
        refresh();
        const created = newOrderPush((ev as MessageEvent).data);
        if (created !== null) announceNewOrder(created);
      };
      ["message", "backstage-orders-update"].forEach((name) => source!.addEventListener(name, onPush));
      source.onopen = () => { realtime.value = "live"; };
      // Erro/desconexão → cai pro poll; o EventSource auto-reconecta e o onopen volta a "live".
      source.onerror = () => { realtime.value = "polling"; };
    } catch {
      source = null; // SSE unavailable → polling carries it.
      realtime.value = "polling";
    }
  }

  // SSE conecta só depois do primeiro fetch do board (sessão/canal prontos):
  // conectar antes disparava um 400 no /sse/orders a cada load.
  function connectWhenReady() {
    if (source) return;
    if (!pending.value && !error.value) { connectSse(); return; }
    watch([pending, error], ([p, e]) => { if (!p && !e) connectSse(); }, { once: true });
  }

  const onVisible = () => {
    if (document.visibilityState !== "visible") return;
    stopTitleAlert(); // o operador voltou — o título para de gritar
    refresh();
  };
  onMounted(() => {
    pollTimer = setInterval(() => refresh(), 30_000);
    connectWhenReady();
    // Voltou à aba / reconectou: refetch imediato (o poll de 30s é longo demais
    // para um pedido iFood novo esperar quando o tablet acabou de acordar).
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    if (source) { source.close(); source = null; }
    stopTitleAlert();
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", onVisible);
  });

  // ── write-side: per-ref in-flight guard + reconcile ──────────────────────
  // Order actions move a card across zones, so an optimistic local move is fragile;
  // instead we mark the ref busy (disables its buttons), POST, then refresh to the
  // server truth. Local + fast, so the refresh feels instant.
  const busy = ref<Set<string>>(new Set());
  const isBusy = (ref_: string) => busy.value.has(ref_);

  // Per-ref action error: the backend's specific, operator-facing reason
  // (e.g. "Pagamento ainda não foi confirmado…"). Kept inline on the card/row —
  // a toast is transient and easy to miss; this persists until dismissed, the
  // next attempt, or a refresh that drops the card.
  const actionErrors = ref<Map<string, string>>(new Map());
  const actionError = (ref_: string) => actionErrors.value.get(ref_) ?? "";
  function setActionError(ref_: string, message: string) {
    const next = new Map(actionErrors.value);
    next.set(ref_, message);
    actionErrors.value = next;
  }
  function clearActionError(ref_: string) {
    if (!actionErrors.value.has(ref_)) return;
    const next = new Map(actionErrors.value);
    next.delete(ref_);
    actionErrors.value = next;
  }

  async function act(ref_: string, action: string, body?: Record<string, unknown>): Promise<boolean> {
    if (busy.value.has(ref_)) return false;
    clearActionError(ref_); // a fresh attempt clears the previous reason
    busy.value = new Set(busy.value).add(ref_);
    try {
      await $fetch(`/api/v1/backstage/orders/${encodeURIComponent(ref_)}/${action}/`, {
        method: "POST",
        body: body ?? {},
      });
      await refresh();
      return true;
    } catch (error) {
      // 409 = o pedido mudou de estado antes da ação chegar (ex.: a confirmação
      // otimista confirmou enquanto o operador recusava). Mensagem honesta, sem
      // fingir que a ação "falhou por bug".
      const conflict = httpError(error).status === 409;
      const message = conflict
        ? httpErrorMessage(error, "O pedido mudou de estado antes da ação chegar.") +
          " Ele pode ter sido confirmado automaticamente. Atualizamos o quadro."
        : httpErrorMessage(error, "Falha na ação. Tente de novo.");
      setActionError(ref_, message);
      useSonner.error(message);
      // Refetch canônico: o estado no servidor pode ter mudado (é justamente o
      // caso do 409) — o quadro precisa mostrar a verdade, não a foto velha.
      await refresh();
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(ref_);
      busy.value = next;
    }
  }

  const confirm = (ref_: string) => act(ref_, "confirm");
  // ``change_out``: troco que o entregador leva da gaveta no despacho (reais);
  // só quando a tela perguntou. O servidor exige o valor quando o pedido pede troco.
  const advance = (ref_: string, changeOut?: string, equipment?: string[]) => {
    const body: Record<string, unknown> = {};
    if (changeOut !== undefined) body.change_out = changeOut;
    if (equipment && equipment.length) body.equipment = equipment;
    return act(ref_, "advance", Object.keys(body).length ? body : undefined);
  };
  // A maquininha voltou com o entregador (pedido que a levou no despacho).
  const equipmentBack = (ref_: string) => act(ref_, "equipment-back");
  // Marketplace (iFood) rejects carry the operator-picked cancellation code so the
  // backend calls requestCancellation with a valid code; empty for other channels.
  const reject = (ref_: string, reason: string, cancellation_code = "") =>
    act(ref_, "reject", { reason, cancellation_code });
  // ``change_back``: o troco que voltou com o entregador (reais, zero vale);
  // obrigatório no servidor quando saiu troco no despacho.
  const settleCash = (ref_: string, amount: string, changeBack?: string, equipmentBack?: boolean) =>
    act(ref_, "settle-delivery-cash", {
      amount,
      ...(changeBack === undefined ? {} : { change_back: changeBack }),
      ...(equipmentBack ? { equipment_back: true } : {}),
    });

  // Valid cancellation reasons for a ref: for iFood, the live per-order list
  // ({code, description}); empty for channels without reason codes.
  async function fetchCancellationReasons(ref_: string): Promise<CancellationReason[]> {
    try {
      const res = await $fetch<{ reasons: CancellationReason[] }>(
        `/api/v1/backstage/orders/${encodeURIComponent(ref_)}/cancellation-reasons/`,
      );
      return res?.reasons ?? [];
    } catch {
      return [];
    }
  }
  const assign = (ref_: string) => act(ref_, "assign");
  const unassign = (ref_: string) => act(ref_, "unassign");

  // Bulk action over many refs: fire all POSTs, capture per-ref failures inline,
  // then refresh once (not per order). Returns how many failed.
  async function actMany(refs: string[], action: string): Promise<number> {
    const targets = refs.filter((r) => !busy.value.has(r));
    if (!targets.length) return 0;
    busy.value = new Set([...busy.value, ...targets]);
    targets.forEach((r) => clearActionError(r));
    let failures = 0;
    await Promise.all(
      targets.map(async (r) => {
        try {
          await $fetch(`/api/v1/backstage/orders/${encodeURIComponent(r)}/${action}/`, { method: "POST", body: {} });
        } catch (error) {
          failures += 1;
          setActionError(r, httpErrorMessage(error, "Falha na ação."));
        }
      }),
    );
    const next = new Set(busy.value);
    targets.forEach((r) => next.delete(r));
    busy.value = next;
    await refresh();
    if (failures) useSonner.error(`${failures} pedido(s) não puderam ser atualizados.`);
    return failures;
  }
  const confirmMany = (refs: string[]) => actMany(refs, "confirm");
  const advanceMany = (refs: string[]) => actMany(refs, "advance");

  return { queue, zones, totalCount, preorders, realtime, pending, error, refresh, isBusy, actionError, clearActionError, confirm, advance, reject, fetchCancellationReasons, settleCash, equipmentBack, equipmentOut, assign, unassign, confirmMany, advanceMany, soundOn, soundBlocked, toggleSound };
}
