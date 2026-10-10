// KDS board read-side (Arc 2). Single source for a station's board:
//   - useFetch the canonical projection (GET /api/v1/backstage/kds/<ref>/);
//   - poll every 15s as a robust fallback (mirrors the HTMX `every 15s`);
//   - SSE realtime: EventSource same-origin no BFF (/sse/kds/<ref> → proxy do
//     eventstream do Django) → refresh on push, and the fanfare while a ticket
//     nobody at the station has seen yet is on the board.
// SSE/poll/beep are client-only (EventSource + Web Audio are browser APIs).
//
// O "Visto" é da ESTAÇÃO, no servidor (K20, prévia v4 nota 3): o ticket chega com
// `seen`, e quem dá Visto numa tela cala as outras telas da mesma estação. O quadro
// é sempre o de hoje (a prévia de outra data foi para a Produção/Encomendas).
// Densidade e som também são da estação (nota 1): o cadastro guarda, e os Ajustes
// gravam lá (`useKdsStationSettings`).
import type { KDSBoardProjection, KDSBoardResponse, KDSTicketProjection } from "~/types/kds";
import { boardView, hasChanges, KDS_UNDO_WINDOW_MS, type KDSBoardView } from "~/presentation/board";
import { openResilientEventSource, type ResilientEventSource } from "../../../operator-kit/app/utils/resilientEventSource";

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

/**
 * O aviso de MUDANÇA no que já estava na cozinha (dono, 10/10/2026: "com alarde, a
 * cada mudança"). Não é figura nova: é a do Gestor, a que o dono escolheu para
 * "atenção, vem informação" (fá → dó, descendo), na voz da casa. A fanfarra sobe e
 * comemora pedido novo; esta desce e pede atenção, então dá para saber pelo ouvido
 * se entrou trabalho ou se algo mudou. Curta (~2 s) e insiste como o pedido novo,
 * até alguém dar a ciência no card.
 */
export const KDS_CHANGE_ALERT = {
  notes: [
    { f: 698.46, t: 0, d: 1.5 },
    { f: 523.25, t: 0.28, d: 1.9 },
  ],
};

/** Os pedidos novos que pedem atenção agora: ticket aberto que ninguém da estação
 *  viu (`seen` vem do servidor). O que mudou toca o aviso de mudança, não este. */
export function kdsAttentionIds(current: KDSBoardView): string[] {
  return current.cards
    .filter((card) => !card.seen && !hasChanges(card) && !current.finishingPks.has(card.pk))
    .map((card) => `active:${card.pk}`)
    .sort();
}

/** As mudanças sem ciência na tela: cada uma tem identidade própria (o card e os
 *  cancelados que ela resume), para que uma mudança NOVA no mesmo card toque de novo. */
export function kdsChangeIds(current: KDSBoardView): string[] {
  return [
    ...current.cards
      .filter(hasChanges)
      .map((card) => `change:${card.pk}:${card.change_ticket_pks.join(".")}:${card.changes.length}`),
    ...current.cancelled.map((card) => `cancelled:${card.pk}`),
  ].sort();
}

/** A mesma régua do pedido novo, para as mudanças: toca o que ainda não anunciou,
 *  cala quando não sobra nenhuma sem ciência. */
export function kdsChangeDecision(
  current: KDSBoardView,
  previousSignature: string,
): { signature: string; shouldAlert: boolean; shouldStop: boolean } {
  const ids = kdsChangeIds(current);
  const signature = ids.join("|");
  const announced = new Set(previousSignature ? previousSignature.split("|") : []);
  return {
    signature,
    shouldAlert: signature !== previousSignature && ids.some((id) => !announced.has(id)),
    shouldStop: ids.length === 0,
  };
}

/** Tocar ou calar. Toca quando aparece um aviso que esta tela ainda não anunciou;
 *  cala quando não sobra nenhum (alguém deu Visto aqui, em outra tela da estação, ou
 *  iniciou o ticket). */
export function kdsAttentionDecision(
  current: KDSBoardView,
  previousSignature: string,
): { signature: string; shouldAlert: boolean; shouldStop: boolean } {
  const ids = kdsAttentionIds(current);
  const signature = ids.join("|");
  const announced = new Set(previousSignature ? previousSignature.split("|") : []);
  return {
    signature,
    shouldAlert: signature !== previousSignature && ids.some((id) => !announced.has(id)),
    shouldStop: ids.length === 0,
  };
}

export function useKdsBoard(stationRef: string) {
  const config = useRuntimeConfig();
  const path = `/api/v1/backstage/kds/${encodeURIComponent(stationRef)}/`;

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
  // A estação sumiu do cadastro (reseed, renomeada, desativada no Admin): o Django
  // responde 404. Não é "sem conexão" — tentar de novo não traz a estação de volta,
  // e o board em cache seria de uma estação que não existe. A tela troca para
  // "escolha outra estação". O poll continua (barato): se a estação voltar com o
  // mesmo ref, o quadro volta sozinho.
  const stationMissing = computed(() => httpError(error.value).status === 404);
  // Marcados Pronto dentro da janela de "Desfazer": o servidor ainda os tem abertos,
  // e a grade também — apagados, no mesmo lugar, com o "Desfazer" ali. A view os
  // tira dos contadores e do "a fazer", então o poll e o SSE não os devolvem ao
  // trabalho enquanto a janela está aberta.
  const finishing = ref<Set<number>>(new Set());
  // O prazo de cada janela aberta (epoch ms): o botão Desfazer conta até ele, e montar
  // o card de novo (foco do celular, recarga da grade) não reinicia a janela.
  const finishUntil = ref<ReadonlyMap<number, number>>(new Map());
  const view = computed<KDSBoardView | null>(() =>
    board.value ? boardView(board.value, finishing.value) : null,
  );

  // Realtime + polling + audio cue (client only). O bloco de áudio (beep 880Hz,
  // mute persistido, desbloqueio de autoplay) é o do kit — chave por estação.
  const {
    soundOn,
    soundBlocked,
    activateSound,
    startAlert,
    stopAlert,
  } = useAlertSound(
    `kds_sound_${stationRef}`,
    KDS_ALERT,
  );
  // O aviso de mudança: a mesma chave de som (ligar e desligar valem para os dois).
  const changeSound = useAlertSound(`kds_sound_${stationRef}`, KDS_CHANGE_ALERT);
  let lastChangeSignature = "";
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: ResilientEventSource | null = null;
  let attentionReady = false;
  let lastAttentionSignature = "";
  // O que está tocando, para a faixa de avisos dizer QUAL pedido é novo ("Pedido novo
  // U13") em vez de um "Visto" solto no cabeçalho.
  const attentionKeys = ref<string[]>([]);
  const attentionPending = computed(() => attentionKeys.value.length > 0);
  // Tempo real honesto (o mesmo padrão do painel de retirada): "ao vivo" só com o SSE
  // de fato aberto; senão o quadro segue no poll de 15 s, e o cabeçalho diz isso.
  const realtime = ref<"connecting" | "live" | "polling">("polling");

  // O som é da estação (o cadastro): quando o quadro chega, o que vale é ele, não o
  // que este dispositivo lembrava.
  watch(
    () => view.value?.soundEnabled,
    (enabled) => {
      if (enabled === undefined) return;
      soundOn.value = enabled;
      changeSound.soundOn.value = enabled;
    },
    { immediate: true },
  );

  function vibrate() {
    if (!import.meta.client || typeof navigator.vibrate !== "function") return;
    if (!window.matchMedia?.("(max-width: 767.98px)").matches) return;
    try {
      navigator.vibrate(400);
    } catch {
      // Navegador sem vibração: o som e a faixa continuam avisando.
    }
  }

  function alertForUnseenWork(current: KDSBoardView) {
    if (!attentionReady || !import.meta.client) return;
    const change = kdsChangeDecision(current, lastChangeSignature);
    lastChangeSignature = change.signature;
    if (change.shouldStop) changeSound.stopAlert();
    if (change.shouldAlert) {
      changeSound.startAlert();
      vibrate();
    }
    const decision = kdsAttentionDecision(current, lastAttentionSignature);
    lastAttentionSignature = decision.signature;
    attentionKeys.value = decision.signature ? decision.signature.split("|") : [];
    if (decision.shouldStop) stopAlert();
    if (decision.shouldAlert) {
      startAlert();
      vibrate();
    }
  }

  // "Visto": grava no servidor, para a estação inteira (K20). Otimista: a faixa some
  // na hora nesta tela; as outras telas da estação calam no SSE que o servidor manda.
  function acknowledgeAttention() {
    const keys = [...attentionKeys.value];
    if (!keys.length) return;
    const pks = keys.map((key) => Number(key.split(":")[1])).filter((pk) => Number.isInteger(pk));
    for (const card of data.value?.board?.tickets ?? []) if (pks.includes(card.pk)) card.seen = true;
    attentionKeys.value = [];
    stopAlert();
    postProxy(`/api/v1/backstage/kds/${encodeURIComponent(stationRef)}/seen/`, {
      method: "POST",
      body: { ticket_pks: pks },
    })
      .then(() => scheduleReconcile())
      .catch((err) => {
        useSonner.error(httpErrorMessage(err, "Não deu para registrar o Visto. Tente de novo."));
        refresh();
      });
  }

  async function activateAttentionSound() {
    await changeSound.primeAudio();
    await activateSound();
  }

  // Som só pertence a quem ninguém viu. A atenção é por identidade, não por
  // contagem: uma troca de tickets que preserve o total ainda precisa avisar.
  watch(() => view.value, (current) => {
    if (!current) return;
    alertForUnseenWork(current);
  }, { immediate: true });

  function connectSse() {
    if (source) return;
    realtime.value = "connecting";
    // Same-origin sempre: o BFF (server/routes/sse/kds/[ref].ts) faz streaming do
    // eventstream do Django, em dev e em prod — nada de gate por origem.
    // django-eventstream pushes named events; any of them means "refetch".
    // Depois do 502 de deploy o EventSource cru ficava CLOSED e a cozinha só
    // via ticket novo no poll de 15 s até recarregar; o do kit se recria, e a
    // reabertura refaz a leitura para cobrir o que passou no meio.
    source = openResilientEventSource({
      url: ssePath(`/sse/kds/${encodeURIComponent(stationRef)}`, config.app.baseURL),
      events: ["backstage-kds-update", "backstage-kds-created", "backstage-kds-status-changed", "backstage-kds-station-changed"],
      onEvent: () => { refresh(); },
      onOpen: (reconnected) => {
        realtime.value = "live";
        if (reconnected) refresh();
      },
      onDown: () => { realtime.value = "polling"; },
    });
  }

  let removeVisibilityListeners: (() => void) | null = null;

  onMounted(() => {
    attentionReady = true;
    if (view.value) alertForUnseenWork(view.value);
    pollTimer = setInterval(() => refresh(), 15_000);
    connectSse();
    // Tablet dormiu / voltou à aba: refetch imediato (setInterval é throttlado em
    // aba oculta), em vez de esperar até 15s por dados possivelmente muito velhos.
    // Tablet que dorme ou fecha com um "Desfazer" aberto: o Pronto vale na hora
    // (keepalive), em vez de sumir com a aba.
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        refresh();
        source?.reconnectNow();
      } else flushFinishes();
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
    return data.value?.board?.tickets?.find((x) => x.pk === pk);
  }

  // Primeiro toque: em preparo. Otimista; reverte e avisa se o servidor recusar.
  function start(pk: number) {
    const t = findTicket(pk);
    if (!t || t.status !== "pending") return;
    t.status = "in_progress";
    t.seen = true;
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

  // Segundo toque: Pronto, com janela de "Desfazer". O POST só sai quando a
  // janela fecha (ou o tablet dorme), então um toque errado não vira "pedido
  // pronto" avisado ao cliente. O aviso e o desfazer vivem NO CARD, que fica no
  // lugar por 5 s: um toast no topo da tela não se alcança com a mão ocupada.
  const finishTimers = new Map<number, ReturnType<typeof setTimeout>>();

  function releaseFinish(pk: number) {
    if (!finishing.value.has(pk)) return;
    const next = new Set(finishing.value);
    next.delete(pk);
    finishing.value = next;
    const deadlines = new Map(finishUntil.value);
    deadlines.delete(pk);
    finishUntil.value = deadlines;
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
        useSonner.error(httpErrorMessage(err, "Falha ao marcar Pronto. Tente de novo."));
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

  const finish = (pk: number) => {
    if (finishTimers.has(pk)) return;
    const t = findTicket(pk);
    if (!t) return;
    finishing.value = new Set(finishing.value).add(pk);
    finishUntil.value = new Map(finishUntil.value).set(pk, Date.now() + KDS_UNDO_WINDOW_MS);
    finishTimers.set(pk, setTimeout(() => commitFinish(pk), KDS_UNDO_WINDOW_MS));
  };
  // Recall: o concluído sai da lista de recentes; a reconciliação o traz de volta ao board ativo.
  const recall = (pk: number) => {
    removeFrom(() => data.value?.board?.recent_done, pk, `/api/v1/backstage/kds/tickets/${pk}/recall/`);
  };
  // Reconhecer cancelado: some do board.
  const acknowledge = (pk: number) => {
    removeFrom(() => data.value?.board?.cancelled_tickets, pk, `/api/v1/backstage/kds/tickets/${pk}/acknowledge/`);
  };

  // A ciência da mudança (dono, 10/10/2026). No card cancelado inteiro é o
  // "Recebi o cancelamento" de sempre (o card sai). No card vivo, o servidor dá baixa
  // nos cancelados que ele resumia e grava o nome que a tela mostrava: só o que a tela
  // mostrou, para uma mudança que chegou depois continuar pedindo ciência. Otimista:
  // a caixa vermelha some na hora e volta, com aviso, se o servidor recusar.
  function acknowledgeChange(pk: number) {
    if (data.value?.board?.cancelled_tickets?.some((card) => card.pk === pk)) {
      acknowledge(pk);
      return;
    }
    const card = findTicket(pk);
    if (!card || !hasChanges(card)) return;
    const before = { changes: card.changes, change_ticket_pks: card.change_ticket_pks, seen: card.seen };
    card.changes = [];
    card.change_ticket_pks = [];
    card.seen = true;
    enqueue(`/api/v1/backstage/kds/tickets/${pk}/changes/seen/`, {
      cancelled_pks: [...before.change_ticket_pks],
      seen_ref: card.order_ref,
    })
      .then(() => scheduleReconcile())
      .catch((err) => {
        Object.assign(card, before);
        useSonner.error(httpErrorMessage(err, "Não deu para registrar a ciência. Tente de novo."));
        refresh();
      });
  }

  // Volumes: quem embalou declara, onde estiver (dono, 04/10/2026). A MESMA porta do
  // Gestor (`orders/<ref>/volumes/`, protocolo de intenção: quem age, a base lida e a
  // chave da tentativa), com `surface: "kds"` para o histórico dizer de onde veio.
  // Zero apaga. Não é otimista: o número só muda na tela quando o servidor gravou.
  const { data: operatorSession } = useNuxtData<{ operator?: { id: number } | null }>("operator-session");
  const volumesBusy = ref(false);
  async function declareVolumes(ticket: KDSTicketProjection, volumes: number): Promise<boolean> {
    if (volumesBusy.value || !ticket.volumes_order_ref) return false;
    volumesBusy.value = true;
    try {
      await postProxy(`/api/v1/backstage/orders/${encodeURIComponent(ticket.volumes_order_ref)}/volumes/`, {
        method: "POST",
        body: {
          volumes,
          surface: "kds",
          expected_actor_id: operatorSession.value?.operator?.id ?? null,
          base_revision: ticket.volumes_revision,
          idempotency_key: crypto.randomUUID(),
        },
      });
      await refresh();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não deu para gravar os volumes. Tente de novo."));
      await refresh();
      return false;
    } finally {
      volumesBusy.value = false;
    }
  }

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
    pending,
    error,
    stationMissing,
    refresh,
    soundOn,
    soundBlocked,
    attentionPending,
    attentionKeys,
    realtime,
    activateAttentionSound,
    acknowledgeAttention,
    start,
    finish,
    finishUntil,
    undoFinish,
    recall,
    acknowledge,
    acknowledgeChange,
    declareVolumes,
    volumesBusy,
  };
}
