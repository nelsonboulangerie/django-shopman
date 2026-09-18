// KDS board read-side (Arc 2). Single source for a station's board:
//   - useFetch the canonical projection (GET /api/v1/backstage/kds/<ref>/);
//   - poll every 15s as a robust fallback (mirrors the HTMX `every 15s`);
//   - SSE realtime: EventSource same-origin no BFF (/sse/kds/<ref> → proxy do
//     eventstream do Django) → refresh on push, and a beep when the
//     active-ticket count rises (new order arrived).
// SSE/poll/beep are client-only (EventSource + Web Audio are browser APIs).
import type { KDSBoardProjection, KDSBoardResponse, KDSTicketProjection } from "~/types/kds";
import {
  boardView,
  KDS_UNDO_WINDOW_MS,
  splitRef,
  type KDSBoardView,
} from "~/presentation/board";
import type { Ref } from "vue";

/**
 * O aviso de ticket novo do KDS — a FANFARRA.
 *
 * ⚠️ Escolhido pelo dono ouvindo os candidatos por cima de um ruído de salão
 * sintetizado, junto com o do Gestor. Não é achismo, e não se mexe sem passar
 * pelo mesmo teste: o que soa bem no fone não sobrevive ao balcão.
 *
 * A VOZ é a da casa (`HOUSE_VOICE`, herdada do kit): gongo macio, ataque de
 * feltro, banda de saguão. É a mesma do Gestor de propósito — as telas do
 * operador têm de soar como a mesma casa.
 *
 * O que muda é a FIGURA, e a figura é a mensagem. O Gestor DESCE (fá → dó:
 * "atenção, vem informação"). A cozinha COMEMORA: três notas correndo para
 * cima e um acorde de dó aberto em três oitavas. Assim dá para saber de que
 * tela veio o som sem olhar para nenhuma das duas.
 *
 * Os pesos por nota (`g`) não são enfeite: as três primeiras entram em
 * crescendo (0,55 → 0,7 → 0,85) e o acorde chega inteiro. É o crescendo que
 * faz isto ser fanfarra em vez de escala.
 *
 * ⚠️ Dura ~2,3 s, e ticket novo chega em RAJADA numa manhã cheia. Se a cozinha
 * achar longo, o ajuste é encurtar as durações do acorde final — não trocar a
 * figura.
 */
export const KDS_ALERT = {
  notes: [
    { f: 783.99, t: 0, d: 0.4, g: 0.55 },
    { f: 1046.5, t: 0.11, d: 0.4, g: 0.7 },
    { f: 1318.51, t: 0.22, d: 0.4, g: 0.85 },
    { f: 1046.5, t: 0.34, d: 2.0 },
    { f: 1567.98, t: 0.34, d: 1.9, g: 0.6 },
    { f: 2093, t: 0.34, d: 1.7, g: 0.35 },
  ],
};

export function kdsAttentionDecision(
  current: KDSBoardView,
  seenIds: ReadonlySet<string>,
  previousSignature: string,
): { signature: string; shouldAlert: boolean; shouldStop: boolean } {
  if (current.serviceDate !== current.today) {
    return { signature: "", shouldAlert: false, shouldStop: true };
  }
  const ids = [
    ...current.cards.map((card) => `active:${card.pk}`),
    ...current.cancelled.map((card) => `cancelled:${card.pk}`),
  ].sort();
  const signature = ids.join("|");
  const noUnseen = ids.every((id) => seenIds.has(id));
  if (signature === previousSignature) {
    return { signature, shouldAlert: false, shouldStop: noUnseen };
  }
  return {
    signature,
    shouldAlert: ids.some((id) => !seenIds.has(id)),
    shouldStop: noUnseen,
  };
}

export function useKdsBoard(stationRef: string, serviceDate?: Ref<string>) {
  const config = useRuntimeConfig();
  const path = computed(() => {
    const base = `/api/v1/backstage/kds/${encodeURIComponent(stationRef)}/`;
    return serviceDate?.value ? `${base}?date=${encodeURIComponent(serviceDate.value)}` : base;
  });

  // useFetch (not useAsyncData) so the SSR payload transfers reliably (POS gotcha).
  const { data, pending, error, refresh } = useFetch<KDSBoardResponse>(path, {
    key: `kds-board-${stationRef}`,
    server: true,
    // O write-side é otimista e MUTA o board por dentro (status do ticket, splice
    // de listas). No Nuxt 4 o `data` do useFetch é raso por padrão: a mutação não
    // re-renderizava, e o toque só aparecia na reconciliação, ~500 ms depois.
    deep: true,
    // Sessão expirou no meio do turno → o poll passa a 401/403. Reabre o gate de
    // operador (re-fetch da sessão) em vez de deixar "reconectando…" para sempre.
    onResponseError: operatorSessionOnError,
  });

  const board = computed<KDSBoardProjection | null>(() => data.value?.board ?? null);
  // Finalizados dentro da janela de "Desfazer": já saíram da grade, o servidor
  // ainda os tem abertos. A view os esconde, então o poll e o SSE não os trazem
  // de volta enquanto a janela está aberta.
  const finishing = ref<Set<number>>(new Set());
  const view = computed<KDSBoardView | null>(() =>
    board.value ? boardView(board.value, finishing.value) : null,
  );

  // Realtime + polling + audio cue (client only). O bloco de áudio (beep 880Hz,
  // mute persistido, desbloqueio de autoplay) é o do kit — chave por estação.
  const {
    soundOn,
    soundBlocked,
    playbackCount,
    toggleSound,
    activateSound,
    startAlert,
    stopAlert,
  } = useAlertSound(
    `kds_sound_${stationRef}`,
    KDS_ALERT,
  );
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: EventSource | null = null;
  let attentionReady = false;
  let lastAttentionSignature = "";
  const attentionPending = ref(false);
  let pendingAttentionIds = new Set<string>();

  const attentionStorageKey = (date: string) => `kds_seen_${stationRef}_${date}`;

  function attentionIds(current: KDSBoardView): string[] {
    return [
      ...current.cards.map((card) => `active:${card.pk}`),
      ...current.cancelled.map((card) => `cancelled:${card.pk}`),
    ];
  }

  function seenAttentionIds(date: string): Set<string> {
    if (!import.meta.client) return new Set();
    try {
      const value = JSON.parse(localStorage.getItem(attentionStorageKey(date)) || "[]");
      return new Set(Array.isArray(value) ? value.map(String) : []);
    } catch {
      return new Set();
    }
  }

  function rememberPendingAttention() {
    const current = view.value;
    if (!current || current.serviceDate !== current.today || !import.meta.client) return;
    const seen = seenAttentionIds(current.serviceDate);
    for (const id of pendingAttentionIds) seen.add(id);
    try {
      // Limite defensivo: a chave é diária, mas um terminal pode ficar semanas
      // sem limpeza. Os mais novos bastam para impedir repetição no remount.
      localStorage.setItem(
        attentionStorageKey(current.serviceDate),
        JSON.stringify([...seen].slice(-500)),
      );
    } catch {
      // Sem storage, a atenção continua válida apenas nesta montagem.
    }
    lastAttentionSignature = attentionIds(current).sort().join("|");
    pendingAttentionIds = new Set();
    attentionPending.value = false;
    stopAlert();
  }

  function acknowledgeAttention() {
    rememberPendingAttention();
  }

  async function activateAttentionSound() {
    await activateSound();
  }

  function alertForUnseenWork(current: KDSBoardView) {
    if (!attentionReady || !import.meta.client) return;
    const seen = seenAttentionIds(current.serviceDate);
    const decision = kdsAttentionDecision(current, seen, lastAttentionSignature);
    lastAttentionSignature = decision.signature;
    if (decision.shouldStop) {
      pendingAttentionIds = new Set();
      attentionPending.value = false;
      stopAlert();
    }
    if (decision.shouldAlert) {
      pendingAttentionIds = new Set(attentionIds(current).filter((id) => !seen.has(id)));
      attentionPending.value = pendingAttentionIds.size > 0;
      startAlert();
    }
  }

  // Tentativa bloqueada pelo autoplay não conta como vista. Só a reprodução
  // efetiva (recibo do kit) ou o botão Ciente persiste os IDs pendentes.
  watch(playbackCount, (count, previous) => {
    if (count > previous && attentionPending.value) rememberPendingAttention();
  });

  // Som só pertence ao quadro de HOJE. A atenção é por identidade, não por
  // contagem: uma troca de tickets que preserve o total ainda precisa avisar. A
  // memória diária também faz um ticket criado de madrugada tocar na primeira
  // abertura, mas não repetir depois que alguém interagiu com o KDS.
  watch(() => view.value, (current) => {
    if (!current) return;
    alertForUnseenWork(current);
  }, { immediate: true });

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
    attentionReady = true;
    if (view.value) alertForUnseenWork(view.value);
    pollTimer = setInterval(() => refresh(), 15_000);
    connectSse();
    // Tablet dormiu / voltou à aba: refetch imediato (setInterval é throttlado em
    // aba oculta), em vez de esperar até 15s por dados possivelmente muito velhos.
    // Tablet que dorme ou fecha com um "Desfazer" aberto: o finalizar vale na hora
    // (keepalive), em vez de sumir com a aba.
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
      else flushFinishes();
    };
    const onPageHide = () => flushFinishes();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
    window.addEventListener("pagehide", onPageHide);
    removeVisibilityListeners = () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onVisible);
      window.removeEventListener("pagehide", onPageHide);
    };
  });

  // ---- write-side: otimista + fila serial + reconciliação ----
  // Toque instantâneo: a UI muda na hora, o POST vai em segundo plano e a fila serial
  // preserva a ordem; uma reconciliação (refresh) ~500ms depois confere com a verdade
  // do servidor. Em falha, reverte o estado local + avisa. Sem `busy` bloqueando —
  // numa cozinha em ritmo, toques em sequência não podem ser descartados.
  let chain: Promise<unknown> = Promise.resolve();
  let reconcileTimer: ReturnType<typeof setTimeout> | null = null;
  const readOnly = computed(() => Boolean(view.value && view.value.serviceDate !== view.value.today));

  // O `$fetch` tipado do Nitro estoura o typecheck (TS2321 excessive stack depth) ao casar
  // um path DINÂMICO contra o catch-all `/api/v1/**:path`. Estas escritas vão pro proxy BFF
  // (a resposta é JSON do Django, NÃO uma rota Nitro tipada), então aqui o $fetch é um cliente
  // HTTP simples — o cast declara isso com precisão (resposta `unknown`) e corta a recursão.
  const postProxy = $fetch as (
    path: string,
    opts: { method: string; body: Record<string, unknown>; keepalive?: boolean },
  ) => Promise<unknown>;

  function scheduleReconcile() {
    if (reconcileTimer) clearTimeout(reconcileTimer);
    reconcileTimer = setTimeout(() => refresh(), 500);
  }

  function enqueue(path: string, body?: Record<string, unknown>) {
    const run = chain.then(() => postProxy(path, { method: "POST", body: body ?? {}, keepalive: true }));
    chain = run.then(() => undefined, () => undefined); // mantém a fila viva após erro
    return run;
  }

  function findTicket(pk: number): KDSTicketProjection | undefined {
    return data.value?.board?.tickets?.find(
      (x) => x.pk === pk && !x.is_expedition,
    ) as KDSTicketProjection | undefined;
  }

  // Primeiro toque: em preparo. Otimista; reverte e avisa se o servidor recusar.
  function start(pk: number) {
    if (readOnly.value) return;
    const t = findTicket(pk);
    if (!t || t.is_scheduled || t.status !== "pending") return;
    t.status = "in_progress";
    enqueue(`/api/v1/backstage/kds/tickets/${pk}/start/`)
      .then(() => scheduleReconcile())
      .catch((err) => {
        t.status = "pending";
        useSonner.error(httpErrorMessage(err, "Falha ao iniciar o preparo."));
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

  // Segundo toque: finalizar — com janela de "Desfazer". O card sai da grade na
  // hora; o POST só sai quando a janela fecha (ou o tablet dorme). Assim um toque
  // errado não vira "pedido pronto" avisado ao cliente.
  const finishTimers = new Map<number, ReturnType<typeof setTimeout>>();

  function releaseFinish(pk: number) {
    if (!finishing.value.has(pk)) return;
    const next = new Set(finishing.value);
    next.delete(pk);
    finishing.value = next;
  }

  function commitFinish(pk: number) {
    const timer = finishTimers.get(pk);
    if (timer === undefined) return;
    clearTimeout(timer);
    finishTimers.delete(pk);
    enqueue(`/api/v1/backstage/kds/tickets/${pk}/done/`)
      .then(async () => {
        await refresh();
        releaseFinish(pk);
      })
      .catch((err) => {
        releaseFinish(pk); // volta para a grade
        useSonner.error(httpErrorMessage(err, "Falha ao finalizar. Tente de novo."));
        refresh();
      });
  }

  function undoFinish(pk: number) {
    const timer = finishTimers.get(pk);
    if (timer === undefined) return;
    clearTimeout(timer);
    finishTimers.delete(pk);
    releaseFinish(pk);
  }

  function flushFinishes() {
    for (const pk of [...finishTimers.keys()]) commitFinish(pk);
  }

  const finalize = (pk: number) => {
    if (readOnly.value || finishTimers.has(pk)) return;
    const t = findTicket(pk);
    if (!t || t.is_scheduled) return;
    finishing.value = new Set(finishing.value).add(pk);
    finishTimers.set(pk, setTimeout(() => commitFinish(pk), KDS_UNDO_WINDOW_MS));
    useSonner.success(`Pedido ${splitRef(t.order_ref).code} finalizado`, {
      duration: KDS_UNDO_WINDOW_MS,
      action: { label: "Desfazer", onClick: () => undoFinish(pk) },
    });
  };
  const expedite = (pk: number, action: "dispatch" | "complete") => {
    if (readOnly.value) return;
    removeFrom(() => data.value?.board?.tickets, pk, `/api/v1/backstage/kds/expedition/${pk}/action/`, { action });
  };
  // Recall: o concluído sai da lista de recentes; a reconciliação o traz de volta ao board ativo.
  const recall = (pk: number) => {
    if (readOnly.value) return;
    removeFrom(() => data.value?.board?.recent_done, pk, `/api/v1/backstage/kds/tickets/${pk}/recall/`);
  };
  // Reconhecer cancelado: some do board.
  const acknowledge = (pk: number) => {
    if (readOnly.value) return;
    removeFrom(() => data.value?.board?.cancelled_tickets, pk, `/api/v1/backstage/kds/tickets/${pk}/acknowledge/`);
  };

  onBeforeUnmount(() => {
    flushFinishes();
    if (pollTimer) clearInterval(pollTimer);
    if (reconcileTimer) clearTimeout(reconcileTimer);
    if (source) { source.close(); source = null; }
    if (removeVisibilityListeners) removeVisibilityListeners();
  });

  return {
    board,
    view,
    readOnly,
    pending,
    error,
    refresh,
    soundOn,
    soundBlocked,
    attentionPending,
    toggleSound,
    activateAttentionSound,
    acknowledgeAttention,
    start,
    finalize,
    undoFinish,
    expedite,
    recall,
    acknowledge,
  };
}
