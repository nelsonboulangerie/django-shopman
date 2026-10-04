<script setup lang="ts">
// Quadro da estação, no desenho da prévia v4 (`cozinha-estacao4.html`, celular em
// `cozinha-celular4.html` (b)). Lê a projection canônica + tempo real (SSE + poll de
// 15 s) por useKdsBoard; os gestos (iniciar, finalizar, desfazer, reabrir, recebi o
// cancelamento) passam pelo proxy do Django (CSRF lá) de forma otimista.
//
// A FILA do cozinheiro: 4 a 6 tickets em foco (3×2 no tablet deitado), o resto vira
// "+N na fila" e entra no "A fazer" (SUITE-UX §10.3). Ticket longo ocupa duas alturas
// em vez de cortar. No celular, um ticket inteiro em foco e os seguintes em linhas.
import type { KDSTicketProjection } from "~/types/kds";
import {
  boardFilterCounts,
  cancelledSummary,
  focusGrid,
  focusSlice,
  matchesBoardFilter,
  realtimeIndicator,
  restSummary,
  shortDateLabel,
  splitRef,
  type KDSBoardFilter,
} from "~/presentation/board";

const route = useRoute();
const router = useRouter();
const stationRef = computed(() => String(route.params.ref || ""));
const serviceDate = computed(() => {
  const value = route.query.date;
  return Array.isArray(value) ? String(value[0] || "") : String(value || "");
});

// Write-side é otimista (toque instantâneo) e mora no composable, junto do estado.
const {
  view,
  readOnly,
  pending,
  error,
  stationMissing,
  soundOn,
  soundBlocked,
  attentionPending,
  attentionKeys,
  realtime,
  toggleSound,
  activateAttentionSound,
  acknowledgeAttention,
  start,
  finalize,
  undoFinish,
  recall,
  acknowledge,
  declareVolumes,
  volumesBusy,
} = useKdsBoard(stationRef.value, serviceDate);

// A estação de Saída não tem tela na Cozinha (UX-G3, SUITE-UX §15: a Saída é a
// coluna Saída do Gestor). Aberta pelo endereço, é estação que não existe aqui.
const notHere = computed(() => stationMissing.value || Boolean(view.value?.isExpedition));
const isToday = computed(() => Boolean(view.value && view.value.serviceDate === view.value.today));
const isPhone = useMediaQuery("(max-width: 767.98px)");

// O shell (rail, Ajustes) sabe da estação: o selo do Preparo, a data de consulta e a
// estação deste dispositivo (o item "Preparo" do rail volta para cá).
const { remember } = useKdsStation();
const boardState = useKdsBoardState();
watch(
  view,
  (current) => {
    if (!current || notHere.value) return;
    remember(stationRef.value, current.instanceName);
    boardState.value = {
      onBoard: true,
      total: current.total,
      serviceDate: current.serviceDate,
      today: current.today,
      availableDates: current.availableDates,
    };
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  boardState.value = { ...boardState.value, onBoard: false };
});

const eyebrow = computed(() => {
  const name = view.value?.instanceName || stationRef.value;
  return /^esta[çc][aã]o\b/i.test(name) ? name : `Estação ${name}`;
});

function handleSoundAction() {
  if (!soundOn.value || soundBlocked.value) {
    void activateAttentionSound();
    return;
  }
  toggleSound();
}
const soundLabel = computed(() => {
  if (soundOn.value && soundBlocked.value) return "Som bloqueado: toque para ativar";
  return soundOn.value ? "Som da estação" : "Som desligado";
});

// A4 — o estado vazio prometia "a gente avisa quando o próximo chegar", e o aviso
// é o SOM: com ele desligado ou bloqueado pelo autoplay, o card entra em silêncio
// numa tela que acabou de convidar a cozinha a não olhar. A frase diz o que de fato
// vai acontecer.
const soundAnnounces = computed(() => soundOn.value && !soundBlocked.value);
const emptyTodayLine = computed(() =>
  soundAnnounces.value
    ? "Nenhum pedido na fila agora. O próximo avisa com som."
    : "Nenhum pedido na fila agora. O som está desligado: o próximo pedido aparece aqui sem avisar.",
);

// Trocar a data é só trocar o endereço (a leitura segue a rota): nada a esperar.
function backToToday() {
  const query = { ...route.query };
  delete query.date;
  void router.replace({ path: route.path, query });
}
const consultLabel = computed(() =>
  view.value && !isToday.value
    ? `Consulta: ${view.value.serviceDateDisplay}, ${shortDateLabel(view.value.serviceDate)}`
    : "",
);

// Recall: painel de concluídos recentes (desfazer finalização).
const recallOpen = ref(false);

// Relógio em tempo real (client-only; new Date() no SSR causaria mismatch).
const now = ref<Date | null>(null);
let clockTimer: ReturnType<typeof setInterval> | null = null;
const clockTime = computed(() =>
  now.value ? now.value.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "",
);
onMounted(() => {
  now.value = new Date();
  clockTimer = setInterval(() => (now.value = new Date()), 1000);
});
onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer);
});

// "Ao vivo" honesto ao lado do título: a hora da última leitura útil, e o estado por
// extenso quando não é tempo real.
const lastRead = ref("");
function markRead() {
  if (import.meta.client && view.value)
    lastRead.value = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}
watch(view, markRead);
onMounted(markRead);
const liveCue = computed(() => realtimeIndicator(realtime.value));
const liveTone = computed(() => {
  if (error.value) return "off" as const;
  return realtime.value === "live" ? ("live" as const) : ("calm" as const);
});
const liveLabel = computed(() => {
  if (error.value) return "Sem conexão";
  return realtime.value === "polling" ? "Atualiza a cada 15 s" : liveCue.value.label;
});

// Densidade (Ajustes): quão estreito o ticket pode ser.
const { density, option: densityOption } = useKdsDensity();

// Busca: filtra por código, cliente ou item. Recortes: Todos, Entrega, Atrasados.
// Contadores e "A fazer" seguem o total da estação: busca e recorte só filtram a grade.
const query = ref("");
const filter = ref<KDSBoardFilter>("all");
const searchInput = ref<{ focus: () => void } | null>(null);
function matchesQuery(card: KDSTicketProjection, q: string): boolean {
  const hay = [card.order_ref, card.customer_name, ...card.items.map((i) => i.name)].join(" ").toLowerCase();
  return hay.includes(q);
}
const tickets = computed(() => (view.value?.cards ?? []) as KDSTicketProjection[]);
const filterCounts = computed(() => boardFilterCounts(tickets.value));
const filteredCards = computed(() => {
  const q = query.value.trim().toLowerCase();
  return tickets.value.filter((card) => matchesBoardFilter(card, filter.value) && (!q || matchesQuery(card, q)));
});
watch(filterCounts, (counts) => {
  if (filter.value !== "all" && counts[filter.value] === 0) filter.value = "all";
});

// A fila em foco: quantos tickets cabem na área (colunas pela densidade, linhas pela
// altura); o resto vira "+N na fila". "Ver a fila inteira" e a busca mostram todos.
const gridBox = ref<HTMLElement | null>(null);
const { width: gridWidth, height: gridHeight } = useElementSize(gridBox);
const expanded = ref(false);
const grid = computed(() => focusGrid({ width: gridWidth.value, height: gridHeight.value }, densityOption.value.min, 10));
const showsEverything = computed(() => expanded.value || Boolean(query.value.trim()));
const slice = computed(() =>
  focusSlice(filteredCards.value, {
    columns: grid.value.columns,
    rows: showsEverything.value ? Number.MAX_SAFE_INTEGER : grid.value.rows,
  }),
);
const rest = computed(() => restSummary(slice.value.rest));
const gridStyle = computed(() => {
  const columns = `repeat(${grid.value.columns}, minmax(0, 1fr))`;
  if (showsEverything.value) return { gridTemplateColumns: columns, gridAutoRows: "minmax(min-content, auto)" };
  return {
    gridTemplateColumns: columns,
    gridTemplateRows: `repeat(${grid.value.rows}, minmax(min-content, 1fr))`,
    minHeight: "100%",
  };
});
function placementStyle(pk: number) {
  const place = slice.value.placements.get(pk);
  if (!place) return {};
  return { gridColumn: String(place.column + 1), gridRow: `${place.row + 1} / span ${place.span}` };
}

// Atalho "/" leva à busca (ensinado no campo).
useEventListener(window, "keydown", (event: KeyboardEvent) => {
  if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
  const target = event.target as HTMLElement | null;
  if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
  event.preventDefault();
  searchInput.value?.focus();
});

// A faixa de avisos: QUAL pedido está tocando ("Pedido novo U13"), com o Visto.
const attentionCodes = computed(() => {
  const codes: string[] = [];
  for (const key of attentionKeys.value) {
    if (!key.startsWith("active:")) continue;
    const card = tickets.value.find((c) => `active:${c.pk}` === key);
    if (card) codes.push(splitRef(card.order_ref).code);
  }
  return codes;
});
const attentionTitle = computed(() => {
  const codes = attentionCodes.value;
  if (!codes.length) return "Aviso novo";
  if (codes.length === 1) return `Pedido novo ${codes[0]}`;
  return `${codes.length} pedidos novos: ${codes.slice(0, 3).join(", ")}${codes.length > 3 ? "…" : ""}`;
});
const activeRefs = computed(() => new Set(tickets.value.map((card) => card.order_ref)));

// Detalhe: o card é leitura de relance; o toque na área de leitura abre o detalhe.
const openTicketPk = ref<number | null>(null);
const openTicket = computed<KDSTicketProjection | null>(() => {
  const pk = openTicketPk.value;
  if (pk == null) return null;
  // O concluído recente também abre: embalar vem depois de finalizar, e os volumes se
  // declaram no detalhe.
  return tickets.value.find((c) => c.pk === pk) ?? view.value?.recentDone.find((c) => c.pk === pk) ?? null;
});
async function onVolumes(count: number) {
  if (openTicket.value) await declareVolumes(openTicket.value, count);
}
function openFromRecent(pk: number) {
  recallOpen.value = false;
  openTicketPk.value = pk;
}
function setModalOpen(value: boolean) {
  if (!value) openTicketPk.value = null;
}

// Toque num pedido travado por item cancelado: o card já diz o que fazer; o aviso
// repete PARA ONDE ir. O gesto se chama "Recebi o cancelamento".
function warnBlocked() {
  useSonner.error(
    "Este pedido tem item cancelado. Confirme o cancelamento no cartão vermelho para poder finalizar.",
  );
}
// Toque no Finalizar travado pelo pagamento: o motivo, com as palavras do servidor.
function warnLocked(pk: number) {
  const card = tickets.value.find((c) => c.pk === pk);
  if (!card) return;
  useSonner.warning(`${card.finish_block_label}. ${card.finish_block_reason}`);
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col md:h-dvh md:flex-none md:overflow-hidden">
    <OperatorPageHeader title="Preparo" :eyebrow="eyebrow">
      <template #status>
        <OperatorLiveStatus :tone="liveTone" :time="lastRead" :label="liveLabel" :detail="liveCue.title" />
        <span
          v-if="consultLabel"
          class="hidden h-6 items-center gap-1.5 rounded-full px-2 text-xs font-semibold pill-warning md:inline-flex"
          data-kds-consult
        >
          <Icon name="lucide:calendar-search" class="size-3.5" />{{ consultLabel }}
        </span>
      </template>
      <template #search>
        <OperatorSuiteSearch
          ref="searchInput"
          v-model="query"
          class="suite:md:w-[19rem]!"
          screen-label="filtrando os tickets"
          placeholder="Código, cliente ou item"
          aria-label="Buscar pedido por código, cliente ou item (atalho: /)"
        />
      </template>
      <template #phone-actions>
        <NotificationBell v-if="isPhone" />
      </template>
      <template #actions>
        <button
          v-if="consultLabel"
          type="button"
          class="inline-flex h-11 items-center gap-2 rounded-md border border-warning/50 px-3.5 op-label font-semibold text-warning transition hover:bg-warning/10"
          data-kds-back-today
          @click="backToToday"
        >
          <Icon name="lucide:calendar-check" class="size-4" />Voltar para hoje
        </button>
        <button
          type="button"
          class="relative inline-flex h-11 items-center gap-2 rounded-md px-3 op-label transition"
          :class="
            soundOn && soundBlocked
              ? 'border border-warning/50 bg-warning/10 font-semibold text-warning'
              : 'bg-muted text-muted-foreground hover:text-foreground'
          "
          :aria-label="soundOn && soundBlocked ? 'Som bloqueado. Toque para ativar' : soundOn ? 'Som ativo. Toque para desligar' : 'Som desligado. Toque para ligar'"
          :aria-pressed="soundOn && !soundBlocked"
          data-kds-sound
          @click="handleSoundAction"
        >
          <Icon
            :name="soundOn ? 'lucide:volume-2' : 'lucide:volume-x'"
            class="size-[18px]"
            :class="soundOn && !soundBlocked ? 'text-success' : ''"
          />
          {{ soundLabel }}
        </button>
        <button
          v-if="view && !readOnly && view.recentDone.length"
          type="button"
          class="inline-flex h-11 items-center gap-2 rounded-md border border-border bg-card px-3.5 op-label font-semibold transition hover:bg-accent"
          :aria-label="`Reabrir concluídos recentes: ${view.recentDone.length}`"
          title="Concluídos nos últimos 30 minutos"
          data-kds-recall
          @click="recallOpen = true"
        >
          <Icon name="lucide:rotate-ccw" class="size-[18px] text-muted-foreground" />
          Reabrir
          <span
            class="grid h-5 min-w-5 place-items-center rounded-full bg-foreground px-1 text-xs font-bold tabular-nums text-background"
            >{{ view.recentDone.length }}</span
          >
        </button>
        <ClientOnly>
          <span v-if="now" class="hidden pl-1 op-figure leading-none md:inline" aria-hidden="true">{{ clockTime }}</span>
        </ClientOnly>
      </template>
    </OperatorPageHeader>

    <section class="flex min-h-0 flex-1 flex-col gap-2 px-3 pt-3 pb-3 md:px-4 md:pt-2.5 md:pb-2">
      <p v-if="pending && !view" class="op-body text-muted-foreground">Carregando…</p>
      <!-- Estação que não existe mais (404): não é falha de conexão, e o board em
           cache seria de uma estação que sumiu. Diz o que houve e leva à lista. -->
      <div
        v-if="notHere"
        class="rounded-lg border border-destructive/30 bg-destructive/5 p-4 op-body text-destructive"
      >
        <p>Esta estação não existe mais. Escolha a estação deste dispositivo na lista.</p>
        <NuxtLink
          to="/"
          class="mt-3 inline-flex h-11 items-center gap-2 rounded-md border px-3 font-medium text-foreground transition hover:bg-accent"
        >
          <Icon name="lucide:list" class="size-4" />
          Ver estações
        </NuxtLink>
      </div>
      <!-- Erro com dados em cache NUNCA apaga o board: um blip de 1 poll não pode
           esconder os tickets da cozinha — banner acima, cards embaixo. -->
      <p
        v-else-if="error && !view"
        class="rounded-lg border border-destructive/30 bg-destructive/5 p-4 op-body text-destructive"
      >
        Não deu para carregar os pedidos desta estação. Tentando de novo.
      </p>
      <p
        v-else-if="error && view"
        class="rounded-lg border border-warning/30 bg-warning/5 px-3 py-2 op-label text-warning"
      >
        Sem conexão: mostrando o último estado. Reconectando…
      </p>

      <template v-if="view && !notHere">
        <!-- AVISOS: pedido novo (Visto) e cancelamentos (Recebi o cancelamento), lado
             a lado do tablet para cima. O vermelho é alerta de verdade só aqui. -->
        <div
          v-if="attentionPending || view.cancelled.length"
          class="flex shrink-0 flex-col gap-2 md:flex-row md:flex-wrap"
          data-kds-notices
        >
          <div
            v-if="attentionPending"
            class="flex min-h-[60px] flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-info/45 bg-info/12 py-1.5 pr-1.5 pl-3 md:min-w-[18rem] md:flex-1"
            data-kds-attention
          >
            <span class="grid size-9 shrink-0 place-items-center rounded-full bg-info/20 text-info">
              <Icon name="lucide:bell-ring" class="size-5" />
            </span>
            <p class="min-w-0 flex-1 basis-[10rem] op-title leading-tight">
              <span class="tabular-nums">{{ attentionTitle }}</span>
              <span class="block op-label font-normal text-muted-foreground">toca neste dispositivo até alguém dar Visto</span>
            </p>
            <button
              type="button"
              class="inline-flex h-12 shrink-0 items-center gap-2 rounded-md bg-foreground px-5 op-title text-background transition hover:bg-foreground/90"
              aria-label="Visto: silenciar o aviso de pedido novo"
              @click="acknowledgeAttention"
            >
              <Icon name="lucide:check" class="size-5" />
              Visto
            </button>
          </div>
          <TransitionGroup tag="div" name="kds-cancel" class="contents">
            <article
              v-for="t in view.cancelled"
              :key="`x-${t.pk}`"
              class="flex min-h-[60px] flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-l-4 border-destructive/45 border-l-destructive bg-destructive/12 py-1.5 pr-1.5 pl-3 md:min-w-[22rem] md:flex-[1.35]"
              data-kds-cancelled
            >
              <div class="min-w-0 flex-1 basis-[14rem] leading-tight">
                <p class="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <b class="text-xl tabular-nums">{{ splitRef(t.order_ref).code }}</b>
                  <span class="inline-flex h-6 items-center gap-1.5 rounded-full px-2 text-xs font-semibold pill-destructive">
                    <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />{{ cancelledSummary(t, activeRefs).label }}
                  </span>
                  <span v-if="cancelledSummary(t, activeRefs).rest" class="op-label text-muted-foreground">{{
                    cancelledSummary(t, activeRefs).rest
                  }}</span>
                </p>
                <p class="mt-0.5 op-label font-semibold break-words line-through decoration-destructive/70">
                  {{ t.items.map((item) => `${item.qty}× ${item.name}`).join(", ") }}
                </p>
              </div>
              <button
                type="button"
                :disabled="readOnly"
                class="inline-flex h-12 shrink-0 items-center gap-2 rounded-md border border-destructive/60 px-4 op-title text-destructive transition hover:bg-destructive/15 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                :aria-label="`Confirmar que a cozinha viu o cancelamento do pedido ${splitRef(t.order_ref).code}`"
                @click="!readOnly && acknowledge(t.pk)"
              >
                <Icon name="lucide:check" class="size-5" />
                Recebi o cancelamento
              </button>
            </article>
          </TransitionGroup>
        </div>

        <!-- A FAZER: o que falta somando a fila INTEIRA (inclusive o "+N"). -->
        <div
          v-if="view.allDay.length && !isPhone"
          class="flex min-h-11 shrink-0 items-center gap-2 overflow-x-auto no-scrollbar"
          data-kds-all-day
        >
          <span class="inline-flex w-[86px] shrink-0 items-center gap-1.5 op-eyebrow text-muted-foreground">
            <Icon name="lucide:clipboard-list" class="size-4" />A fazer
          </span>
          <span
            v-for="entry in view.allDay"
            :key="entry.name"
            class="inline-flex h-10 shrink-0 items-center gap-2 rounded-md border border-border bg-card px-3"
          >
            <b class="text-lg tabular-nums">{{ entry.qty }}×</b>
            <span class="op-body font-medium">{{ entry.name }}</span>
          </span>
        </div>

        <!-- vazio: estação zerada, estado calmo (omotenashi) -->
        <div
          v-if="!view.cards.length"
          class="grid flex-1 place-items-center content-center gap-3 rounded-xl border border-dashed py-16 text-center"
        >
          <div class="grid size-16 place-items-center rounded-full bg-success/10 text-success">
            <Icon name="lucide:coffee" class="size-8" />
          </div>
          <p class="op-display">{{ isToday ? "Tudo em dia" : "Nada agendado" }}</p>
          <p class="max-w-sm op-body text-muted-foreground">
            {{
              isToday
                ? emptyTodayLine
                : `Nenhum item desta estação para ${view.serviceDateDisplay.toLowerCase()}.`
            }}
          </p>
          <button
            v-if="isToday && !soundAnnounces"
            type="button"
            class="inline-flex h-11 items-center gap-1.5 rounded-md border px-3 op-label font-semibold transition hover:bg-accent"
            @click="handleSoundAction"
          >
            <Icon name="lucide:volume-2" class="size-4" />
            Ligar o som
          </button>
        </div>

        <template v-else>
          <!-- cabeça da grade: a ordem e os recortes -->
          <div class="flex min-h-11 shrink-0 flex-wrap items-center gap-2">
            <Icon
              :name="isToday ? 'lucide:arrow-down-wide-narrow' : 'lucide:calendar-search'"
              class="size-4 text-muted-foreground"
            />
            <h2 class="op-eyebrow text-muted-foreground">
              {{ isToday ? "Mais urgente primeiro" : view.serviceDateDisplay }}
            </h2>
            <span class="op-micro text-muted-foreground">
              {{
                isToday
                  ? "· o destacado é o próximo"
                  : `· ${shortDateLabel(view.serviceDate)}: só para consultar. Nada aqui pode ser iniciado ou finalizado hoje.`
              }}
            </span>
            <span class="flex-1" />
            <div class="flex flex-wrap items-center gap-2" role="group" aria-label="Recortes da fila">
              <UiFilterChip :active="filter === 'all'" :count="filterCounts.all" :aria-pressed="filter === 'all'" @click="filter = 'all'">
                <template #icon><Icon v-if="filter === 'all'" name="lucide:check" class="size-4 text-primary" /></template>
                Todos
              </UiFilterChip>
              <UiFilterChip
                v-if="filterCounts.delivery || filter === 'delivery'"
                :active="filter === 'delivery'"
                :count="filterCounts.delivery"
                :aria-pressed="filter === 'delivery'"
                @click="filter = filter === 'delivery' ? 'all' : 'delivery'"
              >
                <template #icon><Icon name="lucide:bike" class="size-4" /></template>
                Entrega
              </UiFilterChip>
              <UiFilterChip
                v-if="filterCounts.late || filter === 'late'"
                :active="filter === 'late'"
                :count="filterCounts.late"
                :aria-pressed="filter === 'late'"
                class="suite:border-destructive/50! suite:text-destructive!"
                @click="filter = filter === 'late' ? 'all' : 'late'"
              >
                <template #icon><Icon name="lucide:timer" class="size-4" /></template>
                Atrasados
              </UiFilterChip>
            </div>
          </div>

          <!-- busca ou recorte sem resultado -->
          <div
            v-if="!filteredCards.length"
            class="grid place-items-center gap-2 rounded-xl border border-dashed py-16 text-center"
          >
            <Icon name="lucide:search-x" class="size-10 text-muted-foreground" />
            <p class="op-title">
              {{ query.trim() ? `Nenhum pedido para “${query.trim()}”.` : "Nenhum pedido neste recorte." }}
            </p>
            <button
              type="button"
              class="min-h-11 px-2 op-label text-muted-foreground underline-offset-2 hover:underline"
              @click="query = ''; filter = 'all'"
            >
              Limpar busca e recorte
            </button>
          </div>

          <!-- celular: um ticket em foco + a fila em linhas -->
          <KdsPhoneQueue
            v-else-if="isPhone"
            :cards="filteredCards"
            :next-pk="query ? null : view.nextPk"
            :blocked-refs="view.blockedRefs"
            :addition-pks="view.additionPks"
            :finishing-pks="view.finishingPks"
            :service-date="view.serviceDate"
            :today="view.today"
            :all-day="view.allDay"
            :density="density"
            @open="(pk) => (openTicketPk = pk)"
            @start="(pk) => !readOnly && start(pk)"
            @finish="(pk) => !readOnly && finalize(pk)"
            @undo="(pk) => undoFinish(pk)"
            @blocked="warnBlocked"
            @locked="warnLocked"
          />

          <!-- tablet e desktop: a fila em foco -->
          <template v-else>
            <div ref="gridBox" class="min-h-0 flex-1 overflow-y-auto" data-kds-grid-box>
              <TransitionGroup tag="div" name="kds-card" class="grid gap-2.5" :style="gridStyle" data-kds-grid>
                <div
                  v-for="card in slice.visible"
                  :key="card.pk"
                  class="flex"
                  :style="placementStyle(card.pk)"
                >
                  <KdsTicketCard
                    :ticket="card"
                    :density="density"
                    :next="!query && filter === 'all' && isToday && card.pk === view.nextPk"
                    :blocked="view.blockedRefs.has(card.order_ref)"
                    :addition="view.additionPks.has(card.pk)"
                    :finishing="view.finishingPks.has(card.pk)"
                    :service-date="view.serviceDate"
                    @open="openTicketPk = card.pk"
                    @start="!readOnly && start(card.pk)"
                    @finish="!readOnly && finalize(card.pk)"
                    @undo="undoFinish(card.pk)"
                    @blocked="warnBlocked"
                    @locked="warnLocked(card.pk)"
                  />
                </div>
              </TransitionGroup>
            </div>
            <!-- o excedente: número e agregado, nunca card minúsculo nem paginação -->
            <button
              v-if="slice.rest.length"
              type="button"
              class="flex min-h-11 shrink-0 flex-wrap items-center justify-center gap-x-2 rounded-lg border border-dashed border-border px-3 op-label text-muted-foreground transition hover:bg-accent"
              data-kds-rest
              @click="expanded = true"
            >
              <b class="text-base tabular-nums text-foreground">{{ rest.count }}</b>
              <span>· {{ rest.detail }}</span>
              <span class="font-semibold text-foreground underline underline-offset-2">Ver a fila inteira</span>
            </button>
            <button
              v-else-if="expanded"
              type="button"
              class="min-h-11 shrink-0 rounded-lg border border-dashed border-border px-3 op-label font-semibold transition hover:bg-accent"
              data-kds-rest-collapse
              @click="expanded = false"
            >
              Voltar à fila em foco
            </button>
          </template>
        </template>
      </template>
    </section>

    <!-- celular: o botão do ticket em foco, no polegar, acima da barra das seções -->
    <div
      v-if="isPhone && view && !notHere && filteredCards.length"
      id="kds-thumb"
      class="sticky bottom-16 z-20 mt-auto bg-gradient-to-t from-background from-70% to-transparent px-3 pt-6 pb-3 md:hidden"
      data-focus-obstruction
    />

    <!-- detalhe (aberto pelo card) -->
    <KdsTicketModal
      :open="openTicket != null"
      :ticket="openTicket"
      :volumes-busy="volumesBusy"
      :read-only="readOnly"
      @update:open="setModalOpen"
      @volumes="onVolumes"
    />

    <!-- recall: concluídos recentes (desfazer finalização) -->
    <UiDialog :open="recallOpen" @update:open="recallOpen = Boolean($event)">
      <UiDialogContent class="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-md" data-suite="v3">
        <UiDialogTitle class="border-b px-5 py-4 op-title">Concluídos recentes</UiDialogTitle>
        <UiDialogDescription class="sr-only"
          >Reabra um pedido finalizado por engano (últimos 30 minutos).</UiDialogDescription
        >
        <div class="min-h-0 flex-1 overflow-y-auto p-3">
          <p v-if="!view || !view.recentDone.length" class="p-6 text-center op-body text-muted-foreground">
            Nada concluído nos últimos 30 minutos.
          </p>
          <ul v-else class="flex flex-col gap-1.5">
            <li
              v-for="t in view.recentDone"
              :key="t.pk"
              class="flex items-center justify-between gap-3 rounded-lg border p-3"
            >
              <div class="min-w-0">
                <p class="truncate text-lg font-bold tabular-nums leading-tight">
                  {{ splitRef(t.order_ref).code }}
                </p>
                <p class="truncate op-label text-muted-foreground">
                  {{ t.customer_name || t.order_ref
                  }}<template v-if="t.completed_at_display"> · {{ t.completed_at_display }}</template>
                </p>
              </div>
              <button
                v-if="t.volumes_order_ref && !readOnly"
                type="button"
                class="ml-auto inline-flex h-11 shrink-0 items-center gap-1.5 rounded-md border px-3 op-label font-semibold transition hover:bg-accent active:scale-[0.98]"
                :aria-label="`Volumes do pedido ${splitRef(t.order_ref).code}`"
                data-kds-recent-volumes
                @click="openFromRecent(t.pk)"
              >
                <Icon name="lucide:package" class="size-4" />
                {{ t.volumes ? t.volumes : "Volumes" }}
              </button>
              <button
                type="button"
                :disabled="readOnly"
                class="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-md border px-3 op-label font-semibold transition hover:bg-accent active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                @click="!readOnly && recall(t.pk)"
              >
                <Icon name="lucide:rotate-ccw" class="size-4" />
                Reabrir
              </button>
            </li>
          </ul>
        </div>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>

<style scoped>
/* Transição da grade: ao finalizar, o card sai com um respiro e a fila desliza (FLIP),
   o próximo "assume o foco". Novos pedidos entram com o mesmo respiro. */
.kds-card-move {
  transition: transform 0.35s cubic-bezier(0.2, 0, 0, 1);
}
.kds-card-enter-active,
.kds-card-leave-active {
  transition:
    opacity 0.28s ease,
    transform 0.28s ease;
}
.kds-card-enter-from,
.kds-card-leave-to {
  opacity: 0;
  transform: scale(0.96);
}

/* Cancelamento entra duas vezes com um pulso curto: atenção inequívoca, sem manter o
   board inteiro piscando. "Recebi o cancelamento" encerra o estado. */
.kds-cancel-enter-active {
  animation: kds-cancel-attention 0.7s ease-in-out 2;
}
@keyframes kds-cancel-attention {
  0%,
  100% {
    transform: translateX(0) scale(1);
  }
  30% {
    transform: translateX(-5px) scale(1.015);
  }
  60% {
    transform: translateX(5px) scale(1.015);
  }
}

@media (prefers-reduced-motion: reduce) {
  .kds-card-move,
  .kds-card-enter-active,
  .kds-card-leave-active {
    transition: none;
  }
  .kds-cancel-enter-active {
    animation: none;
  }
}
</style>
