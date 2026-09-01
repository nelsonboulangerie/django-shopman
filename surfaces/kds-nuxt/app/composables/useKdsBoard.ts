// KDS board read-side (Arc 2). Single source for a station's board:
//   - useFetch the canonical projection (GET /api/v1/backstage/kds/<ref>/);
//   - poll every 15s as a robust fallback (mirrors the HTMX `every 15s`);
//   - SSE realtime: EventSource same-origin no BFF (/sse/kds/<ref> → proxy do
//     eventstream do Django) → refresh on push, and a beep when the
//     active-ticket count rises (new order arrived).
// SSE/poll/beep are client-only (EventSource + Web Audio are browser APIs).
import type { KDSBoardProjection, KDSBoardResponse, KDSTicketProjection } from "~/types/kds";
import { boardView, type KDSBoardView } from "~/presentation/board";

export function useKdsBoard(stationRef: string) {
  const config = useRuntimeConfig();
  const path = `/api/v1/backstage/kds/${encodeURIComponent(stationRef)}/`;

  // useFetch (not useAsyncData) so the SSR payload transfers reliably (POS gotcha).
  const { data, pending, error, refresh } = useFetch<KDSBoardResponse>(path, {
    key: `kds-board-${stationRef}`,
    server: true,
    // Sessão expirou no meio do turno → o poll passa a 401/403. Reabre o gate de
    // operador (re-fetch da sessão) em vez de deixar "reconectando…" para sempre.
    onResponseError: operatorSessionOnError,
  });

  const board = computed<KDSBoardProjection | null>(() => data.value?.board ?? null);
  const view = computed<KDSBoardView | null>(() => (board.value ? boardView(board.value) : null));

  // Realtime + polling + audio cue (client only). O bloco de áudio (beep 880Hz,
  // mute persistido, desbloqueio de autoplay) é o do kit — chave por estação.
  const { soundOn, soundBlocked, toggleSound, beep } = useAlertSound(`kds_sound_${stationRef}`);
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: EventSource | null = null;
  let lastTotal = -1;

  // Beep when the active total rises (a new ticket arrived on this station).
  watch(() => view.value?.total ?? 0, (total) => {
    if (lastTotal >= 0 && total > lastTotal) beep();
    lastTotal = total;
  });

  function connectSse() {
    if (source) return;
    // Same-origin sempre: o BFF (server/routes/sse/kds/[ref].ts) faz streaming do
    // eventstream do Django, em dev e em prod — nada de gate por origem.
    const url = ssePath(`/sse/kds/${encodeURIComponent(stationRef)}`, config.app.baseURL);
    try {
      source = new EventSource(url, { withCredentials: true });
      // django-eventstream pushes named events; any of them means "refetch".
      const onPush = () => { refresh(); };
      ["message", "backstage-kds-update", "backstage-kds-created", "backstage-kds-status-changed", "backstage-kds-station-changed"]
        .forEach((name) => source!.addEventListener(name, onPush));
      source.onerror = () => { /* EventSource auto-reconnects; poll covers gaps. */ };
    } catch {
      source = null; // SSE unavailable → polling carries it.
    }
  }

  let removeVisibilityListeners: (() => void) | null = null;

  onMounted(() => {
    lastTotal = view.value?.total ?? -1;
    pollTimer = setInterval(() => refresh(), 15_000);
    connectSse();
    // Tablet dormiu / voltou à aba: refetch imediato (setInterval é throttlado em
    // aba oculta), em vez de esperar até 15s por dados possivelmente muito velhos.
    const onVisible = () => { if (document.visibilityState === "visible") refresh(); };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
    removeVisibilityListeners = () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onVisible);
    };
  });

  // ---- write-side: otimista + fila serial + reconciliação ----
  // Toque instantâneo: a UI muda na hora, o POST vai em segundo plano e a fila serial
  // preserva a ordem; uma reconciliação (refresh) ~500ms depois confere com a verdade
  // do servidor. Em falha, reverte o estado local + avisa. Sem `busy` bloqueando —
  // numa cozinha em ritmo, toques em sequência não podem ser descartados.
  let chain: Promise<unknown> = Promise.resolve();
  let reconcileTimer: ReturnType<typeof setTimeout> | null = null;

  // O `$fetch` tipado do Nitro estoura o typecheck (TS2321 excessive stack depth) ao casar
  // um path DINÂMICO contra o catch-all `/api/v1/**:path`. Estas escritas vão pro proxy BFF
  // (a resposta é JSON do Django, NÃO uma rota Nitro tipada), então aqui o $fetch é um cliente
  // HTTP simples — o cast declara isso com precisão (resposta `unknown`) e corta a recursão.
  const postProxy = $fetch as (
    path: string,
    opts: { method: string; body: Record<string, unknown> },
  ) => Promise<unknown>;

  function scheduleReconcile() {
    if (reconcileTimer) clearTimeout(reconcileTimer);
    reconcileTimer = setTimeout(() => refresh(), 500);
  }

  function enqueue(path: string, body?: Record<string, unknown>) {
    const run = chain.then(() => postProxy(path, { method: "POST", body: body ?? {} }));
    chain = run.then(() => undefined, () => undefined); // mantém a fila viva após erro
    return run;
  }

  function checkItem(pk: number, index: number, checked: boolean) {
    const t = data.value?.board?.tickets?.find((x) => x.pk === pk && "items" in x) as KDSTicketProjection | undefined;
    const item = t?.items?.[index];
    if (!t || !item) return;
    const prev = item.checked;
    item.checked = checked; // otimista
    t.all_checked = t.items.every((i) => i.checked);
    enqueue(`/api/v1/backstage/kds/tickets/${pk}/items/`, { index, checked })
      .then(() => scheduleReconcile())
      .catch((err) => {
        item.checked = prev; // reverte
        t.all_checked = t.items.every((i) => i.checked);
        useSonner.error(httpErrorMessage(err, "Falha ao marcar item."));
        refresh();
      });
  }

  // Remove um card de uma lista do board (tickets / cancelled / recent_done) na hora
  // e dispara o POST; recoloca + avisa em falha; reconcilia ~500ms depois.
  function removeFrom<T extends { pk: number }>(
    getList: () => T[] | undefined,
    pk: number,
    path: string,
    body?: Record<string, unknown>,
  ) {
    const list = getList();
    const idx = list?.findIndex((x) => x.pk === pk) ?? -1;
    if (!list || idx < 0) return;
    const [removed] = list.splice(idx, 1);
    enqueue(path, body)
      .then(() => scheduleReconcile())
      .catch((err) => {
        if (removed) getList()?.splice(idx, 0, removed);
        useSonner.error(httpErrorMessage(err, "Falha na ação. Tente de novo."));
        refresh();
      });
  }

  const finalize = (pk: number) =>
    removeFrom(() => data.value?.board?.tickets, pk, `/api/v1/backstage/kds/tickets/${pk}/done/`);
  const expedite = (pk: number, action: "dispatch" | "complete") =>
    removeFrom(() => data.value?.board?.tickets, pk, `/api/v1/backstage/kds/expedition/${pk}/action/`, { action });
  // Recall: o concluído sai da lista de recentes; a reconciliação o traz de volta ao board ativo.
  const recall = (pk: number) =>
    removeFrom(() => data.value?.board?.recent_done, pk, `/api/v1/backstage/kds/tickets/${pk}/recall/`);
  // Reconhecer cancelado: some do board.
  const acknowledge = (pk: number) =>
    removeFrom(() => data.value?.board?.cancelled_tickets, pk, `/api/v1/backstage/kds/tickets/${pk}/acknowledge/`);

  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    if (reconcileTimer) clearTimeout(reconcileTimer);
    if (source) { source.close(); source = null; }
    if (removeVisibilityListeners) removeVisibilityListeners();
  });

  return { board, view, pending, error, refresh, soundOn, soundBlocked, toggleSound, checkItem, finalize, expedite, recall, acknowledge };
}
