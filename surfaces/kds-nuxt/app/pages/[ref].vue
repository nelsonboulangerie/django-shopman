<script setup lang="ts">
// Quadro da estação, no desenho da prévia v4 (`cozinha-estacao4.html`, celular em
// `cozinha-celular4.html` (b)), dentro do shell da suíte (fase 2). Lê a projection
// canônica + tempo real (SSE + poll de 15 s) por useKdsBoard; os gestos (iniciar,
// Pronto, desfazer, reabrir, recebi o cancelamento, visto) passam pelo proxy do Django
// (CSRF lá) de forma otimista.
//
// A FILA do cozinheiro: 4 a 6 tickets em foco (3×2 no tablet deitado), o resto vira
// "+N na fila" e entra no "A fazer" (SUITE-UX §10.3), sempre na ordem de leitura, com a
// posição escrita no ticket (Agora, Próximo, Depois). No celular, um ticket inteiro em foco e os seguintes em linhas, o
// ato na base (`OperatorActionBar`, "Pronto W07"), deslizar a linha para Pronto (F7) e
// ver o pedido, desfazer e reabrir no toque longo.
//
// Os avisos da tela (cancelamento, pedido novo tocando, som bloqueado) moram no
// `alerts` do cabeçalho, cada um com a ação que o resolve; o estado da leitura
// (carregando, erro, sem conexão, vazio) é o `OperatorScreenState` do kit.
//
// O quadro é sempre o de HOJE (nota 2: a prévia de outra data foi para a Produção/
// Encomendas). Densidade e som são da estação provisionada (nota 1, Ajustes).
import type { OperatorActionBarAction } from "../../../operator-kit/app/presentation/actionBar";
import type { OperatorHeaderAction } from "../../../operator-kit/app/presentation/pageHeader";
import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";
import type { KDSTicketProjection } from "~/types/kds";
import {
  boardFilterCounts,
  cancelledAlert,
  elapsedLabel,
  focusGrid,
  focusSlice,
  KDS_ARM_DELAY_MS,
  KDS_UNDO_WINDOW_MS,
  matchesBoardFilter,
  realtimeIndicator,
  queuePositionLabel,
  restSummary,
  splitRef,
  ticketAction,
  ticketOverline,
  type KDSBoardFilter,
} from "~/presentation/board";

const route = useRoute();
const stationRef = computed(() => String(route.params.ref || ""));

// Write-side é otimista (toque instantâneo) e mora no composable, junto do estado.
const {
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
  undoFinish,
  finishUntil,
  recall,
  acknowledge,
  declareVolumes,
  volumesBusy,
} = useKdsBoard(stationRef.value);

const notHere = computed(() => stationMissing.value);
// A régua da suíte (`useScreen` do kit) responde "mesa" até a hidratação terminar. Para
// o celular não nascer com o quadro da mesa e trocar de árvore na frente de quem olha,
// antes de hidratar as DUAS variantes vão no HTML e o CSS mostra a certa (`md:hidden`
// / `max-md:hidden`); depois, a que não serve sai da árvore.
const screen = useScreen();
const isPhone = screen.belowMd;
const phoneVariant = computed(() => !screen.ready.value || isPhone.value);
const deskVariant = computed(() => !screen.ready.value || !isPhone.value);

// O shell (barras, Ajustes) sabe da estação: o selo dela, a densidade e o som e a
// estação deste dispositivo (a que vai à frente na barra inferior).
// ⚠️ Só depois de montar: o shell é desenhado no servidor antes de o quadro ter dados,
// e gravar aqui durante o setup fazia a hidratação do cliente ver um shell diferente do
// que o servidor mandou (selo e rótulos). Depois de montar, a troca é reatividade comum.
const { remember } = useKdsStation();
const boardState = useKdsBoardState();
function shareWithShell(current: typeof view.value) {
  if (!current || notHere.value) return;
  remember(stationRef.value, current.instanceName);
  boardState.value = {
    onBoard: true,
    total: current.total,
    stationRef: stationRef.value,
    stationName: current.instanceName,
    density: current.density,
    soundEnabled: current.soundEnabled,
  };
}
onMounted(() => {
  shareWithShell(view.value);
  watch(view, shareWithShell);
});
onBeforeUnmount(() => {
  boardState.value = { ...boardState.value, onBoard: false };
});

// O título é o NOME da estação (Cafés, Lanches): estação é um posto específico, e não
// existe estação chamada "Preparo" (dono, 09/10/2026). É o mesmo nome do item aceso na
// navegação.
const stationTitle = computed(() => view.value?.instanceName || stationRef.value);

// O som é da estação (Ajustes). O navegador que bloqueia o áudio vira aviso da tela,
// com "Ativar o som"; ligar e desligar é dos Ajustes (o ⋯ diz o estado no rótulo).
const settingsOpen = useKdsSettingsOpen();
function handleSoundAction() {
  if (soundOn.value && soundBlocked.value) {
    void activateAttentionSound();
    return;
  }
  settingsOpen.value = true;
}

// A4: o estado vazio prometia "a gente avisa quando o próximo chegar", e o aviso é o
// SOM: com ele desligado ou bloqueado pelo autoplay, o card entra em silêncio numa tela
// que acabou de convidar a cozinha a não olhar. A frase diz o que de fato vai acontecer.
const soundAnnounces = computed(() => soundOn.value && !soundBlocked.value);
const emptyTodayLine = computed(() =>
  soundAnnounces.value
    ? "Nenhum pedido na fila agora. O próximo avisa com som."
    : "Nenhum pedido na fila agora. O som está desligado: o próximo pedido aparece aqui sem avisar.",
);

// Recall: painel de concluídos recentes (desfazer o Pronto).
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
  return realtime.value === "polling" ? "Atualiza sozinho a cada 15 s" : liveCue.value.label;
});

// Densidade da estação (Ajustes): quão estreito o ticket pode ser.
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
const tickets = computed(() => view.value?.cards ?? []);
const filterCounts = computed(() => boardFilterCounts(tickets.value));
const filteredCards = computed(() => {
  const q = query.value.trim().toLowerCase();
  return tickets.value.filter((card) => matchesBoardFilter(card, filter.value) && (!q || matchesQuery(card, q)));
});
watch(filterCounts, (counts) => {
  if (filter.value !== "all" && counts[filter.value] === 0) filter.value = "all";
});
// No celular não há recortes (prévia v4 b): a fila inteira, a mais urgente primeiro.
watch(isPhone, (phone) => {
  if (phone) filter.value = "all";
});
// Os recortes na toolbar (só da mesa): os filtros rápidos da suíte, um de cada vez,
// com a contagem; Entrega e Atrasados só aparecem quando há o que mostrar.
const filterTabs = computed(() => {
  const counts = filterCounts.value;
  return [
    { key: "all", label: "Todos", count: counts.all },
    ...(counts.delivery || filter.value === "delivery"
      ? [{ key: "delivery", label: "Entrega", icon: "i-lucide-bike", count: counts.delivery }]
      : []),
    ...(counts.late || filter.value === "late"
      ? [
          {
            key: "late",
            label: "Atrasados",
            icon: "i-lucide-timer",
            count: counts.late,
          },
        ]
      : []),
  ];
});
const filterModel = computed({
  get: () => filter.value as string,
  set: (value: string | string[]) => {
    filter.value = String(value) as KDSBoardFilter;
  },
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
// A grade em LINHAS, na ordem de leitura (dono, 09/10/2026): cada ticket tem a altura
// do PRÓPRIO conteúdo (`self-start`, nunca esticado), e a linha seguinte começa abaixo
// do ticket mais alto da linha de cima. Cada ticket tem a sua célula, posta
// explicitamente na ordem da fila (`focusSlice`): nunca `grid-auto-flow: dense`,
// masonry nem colunas CSS, que reordenam a fila na tela.
const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${grid.value.columns}, minmax(0, 1fr))`,
  gridAutoRows: "auto",
  alignItems: "start",
  alignContent: "start",
}));
// A posição de ataque escrita em cada ticket da mesa (Agora, Próximo, Depois), contada
// sobre a fila inteira sem os que estão na janela do Desfazer. Com busca ou recorte a
// grade mostra um pedaço da fila, e a posição sai junto com o destaque do próximo.
const positions = computed(() => {
  const map = new Map<number, string>();
  if (query.value.trim() || filter.value !== "all" || !view.value) return map;
  view.value.cards
    .filter((card) => !view.value!.finishingPks.has(card.pk))
    .forEach((card, index) => map.set(card.pk, queuePositionLabel(index)));
  return map;
});
function placementStyle(pk: number) {
  const place = slice.value.placements.get(pk);
  if (!place) return {};
  return { gridColumn: String(place.column + 1), gridRow: String(place.row + 1) };
}

// Atalho "/" leva à busca (ensinado no campo).
useEventListener(window, "keydown", (event: KeyboardEvent) => {
  if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
  const target = event.target as HTMLElement | null;
  if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
  event.preventDefault();
  searchInput.value?.focus();
});

// O aviso do pedido novo: QUAL pedido está tocando ("Pedido novo U13"), com o Visto.
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

// Os avisos da tela, na ordem da gravidade: o cancelamento (trava o Pronto e diz o que
// não preparar), o pedido novo que está tocando e o som que o navegador bloqueou. O
// primeiro aparece inteiro; os outros ficam em "e mais N" (regra do kit).
const screenAlerts = computed<OperatorScreenAlert[]>(() => {
  const current = view.value;
  if (!current || notHere.value) return [];
  const alerts: OperatorScreenAlert[] = current.cancelled.map((cancelled) => {
    const copy = cancelledAlert(cancelled, activeRefs.value);
    return {
      id: `cancelled-${cancelled.pk}`,
      color: "error",
      icon: "i-lucide-ban",
      title: copy.title,
      description: copy.description,
      action: { label: "Recebi o cancelamento", onSelect: () => void acknowledge(cancelled.pk) },
    };
  });
  if (attentionPending.value) {
    alerts.push({
      id: "attention",
      color: "info",
      icon: "i-lucide-bell-ring",
      title: attentionTitle.value,
      description: "Toca nesta estação até alguém dar Visto.",
      action: { label: "Visto", onSelect: () => void acknowledgeAttention() },
    });
  }
  if (soundOn.value && soundBlocked.value) {
    alerts.push({
      id: "sound-blocked",
      color: "warning",
      icon: "i-lucide-volume-x",
      title: "O navegador bloqueou o som desta estação",
      description: "Pedido novo entra sem tocar até alguém ativar o som.",
      action: { label: "Ativar o som", onSelect: () => void activateAttentionSound() },
    });
  }
  return alerts;
});

// O ⋯ "Mais ações": o que age na tela inteira. Reabrir (desfazer um Pronto de até 30
// minutos), os Ajustes da estação com o estado do som no rótulo, e Atualizar.
const headerActions = computed<OperatorHeaderAction[]>(() => {
  const recent = view.value?.recentDone.length ?? 0;
  return [
    {
      label: recent ? `Reabrir um concluído (${recent})` : "Reabrir um concluído",
      icon: "i-lucide-rotate-ccw",
      disabled: !recent,
      reason: recent ? undefined : "Nada concluído nos últimos 30 minutos.",
      onSelect: () => {
        recallOpen.value = true;
      },
    },
    {
      label: soundOn.value ? "Ajustes da estação (som ligado)" : "Ajustes da estação (som desligado)",
      icon: soundOn.value ? "i-lucide-volume-2" : "i-lucide-volume-x",
      onSelect: () => {
        settingsOpen.value = true;
      },
    },
    { label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => void refresh() },
  ];
});

// Detalhe: o card é leitura de relance; o toque na área de leitura abre o detalhe.
const openTicketPk = ref<number | null>(null);
const openTicket = computed<KDSTicketProjection | null>(() => {
  const pk = openTicketPk.value;
  if (pk == null) return null;
  // O concluído recente também abre: embalar vem depois do Pronto, e os volumes se
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

// O ticket em foco no celular: o tocado (ou o deslizado para Pronto), senão o primeiro
// da fila. O ato dele mora na ação na base.
const chosenPk = ref<number | null>(null);
const phoneFocus = computed<KDSTicketProjection | null>(
  () => filteredCards.value.find((card) => card.pk === chosenPk.value) ?? filteredCards.value[0] ?? null,
);
// Armar o Pronto na base: o botão fica no MESMO lugar ao passar de Iniciar para Pronto,
// então o toque que iniciou não pode, quicando, marcar Pronto também (a mesma janela do
// card, `KDS_ARM_DELAY_MS`).
const barArmed = ref(true);
let barArmTimer: ReturnType<typeof setTimeout> | null = null;
watch(
  () => [phoneFocus.value?.pk, phoneFocus.value?.status] as const,
  ([pk, status], [previousPk, previousStatus]) => {
    if (barArmTimer) clearTimeout(barArmTimer);
    if (pk === previousPk && previousStatus === "pending" && status === "in_progress") {
      barArmed.value = false;
      barArmTimer = setTimeout(() => (barArmed.value = true), KDS_ARM_DELAY_MS);
    } else {
      barArmed.value = true;
    }
  },
);
onBeforeUnmount(() => {
  if (barArmTimer) clearTimeout(barArmTimer);
});
const phoneAction = computed<OperatorActionBarAction | null>(() => {
  const card = phoneFocus.value;
  const current = view.value;
  if (!card || !current) return null;
  const code = splitRef(card.order_ref).code;
  const action = ticketAction(card, {
    armed: barArmed.value,
    blocked: current.blockedRefs.has(card.order_ref),
    finishing: current.finishingPks.has(card.pk),
  });
  switch (action.kind) {
    case "start":
      return { label: `Iniciar ${code}`, icon: "i-lucide-play", onSelect: () => void start(card.pk) };
    case "finish":
      return {
        label: `Pronto ${code}`,
        icon: "i-lucide-check",
        disabled: !action.enabled,
        onSelect: () => void finish(card.pk),
      };
    case "blocked":
      return {
        label: `Pronto ${code}`,
        icon: "i-lucide-ban",
        disabled: true,
        reason: "Item cancelado neste pedido. Toque em Recebi o cancelamento, no aviso do topo.",
      };
    case "locked":
      return {
        label: `Pronto ${code}`,
        icon: "i-lucide-lock",
        disabled: true,
        reason: `${card.finish_block_label}. ${card.finish_block_reason}`,
      };
    // O Desfazer mora no MESMO botão da base onde o Pronto foi tocado (dono,
    // 09/10/2026): a barra não muda, só o texto, e o fundo esvazia atrás dele.
    case "undo": {
      const until = finishUntil.value.get(card.pk);
      if (!until) return null;
      return {
        label: `Desfazer ${code}`,
        icon: "i-lucide-undo-2",
        ariaLabel: `Desfazer o Pronto do pedido ${code}`,
        timed: { until, duration: KDS_UNDO_WINDOW_MS },
        onSelect: () => void undoFinish(card.pk),
      };
    }
    default:
      return null;
  }
});
const phoneContext = computed(() => {
  const card = phoneFocus.value;
  if (!card) return { label: "", value: "" };
  return {
    label: `${splitRef(card.order_ref).code} · ${ticketOverline(card)}`,
    value: elapsedLabel(card.elapsed_seconds),
  };
});

// Toque longo no celular (prévia v4 nota 7): o menu do pedido com ver o pedido,
// desfazer e reabrir.
const heldPk = ref<number | null>(null);
const heldTicket = computed(() => tickets.value.find((card) => card.pk === heldPk.value) ?? null);
const holdOpen = computed({
  get: () => heldPk.value != null,
  set: (value: boolean) => {
    if (!value) heldPk.value = null;
  },
});
function onHold(pk: number) {
  heldPk.value = pk;
}

// O celular da estação pequena leva a estação no bolso: o pedido novo chega por push
// e vibra com a tela apagada (SUITE-UX §10.3, prévia v4 b). Abrir o quadro no celular
// segue a estação por um turno (o servidor guarda; seguir outra deixa esta).
const push = useWebPush();
onMounted(() => {
  if (!isPhone.value) return;
  void ($fetch as (path: string, opts: { method: string; body: Record<string, unknown> }) => Promise<unknown>)(
    `/api/v1/backstage/kds/${encodeURIComponent(stationRef.value)}/follow/`,
    { method: "POST", body: {} },
  ).catch(() => {
    // Sem seguir, o quadro continua avisando com som enquanto a tela está acesa.
  });
});

// Toque num pedido travado por item cancelado: o card já diz o que fazer; o aviso
// repete PARA ONDE ir. O gesto se chama "Recebi o cancelamento".
function warnBlocked() {
  useSonner.error(
    "Este pedido tem item cancelado. Toque em Recebi o cancelamento, no aviso vermelho do topo, para poder marcar Pronto.",
  );
}
// Toque no Pronto travado pelo pagamento: o motivo, com as palavras do servidor.
function warnLocked(pk: number) {
  const card = tickets.value.find((c) => c.pk === pk);
  if (!card) return;
  useSonner.warning(`${card.finish_block_label}. ${card.finish_block_reason}`);
}
function clearSearchAndFilter() {
  query.value = "";
  filter.value = "all";
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      :title="stationTitle"
      :alerts="screenAlerts"
      :actions="headerActions"
      desk-only-filters
    >
      <template #status>
        <OperatorLiveStatus :tone="liveTone" :time="lastRead" :label="liveLabel" :detail="liveCue.title" />
      </template>
      <template #search>
        <OperatorSuiteSearch
          ref="searchInput"
          v-model="query"
          screen-label="filtrando os tickets"
          placeholder="Código, cliente ou item"
          aria-label="Buscar pedido por código, cliente ou item (atalho: /)"
        />
      </template>
      <!-- Na mesa, a hora de relance; o resto age pelo ⋯ "Mais ações". -->
      <template #actions>
        <ClientOnly>
          <span v-if="now" class="hidden pl-1 op-figure leading-none md:inline" aria-hidden="true">{{ clockTime }}</span>
        </ClientOnly>
      </template>
      <!-- Os recortes da fila (só na mesa: o celular mostra a fila inteira, a mais
           urgente primeiro, prévia v4 b). -->
      <template v-if="tickets.length" #filters>
        <OperatorQuickFilters
          v-model="filterModel"
          :items="filterTabs"
          label="Recortes da fila"
          data-kds-filters
        />
        <span class="text-sm text-muted-foreground">Mais urgente primeiro, da esquerda para a direita.</span>
      </template>
    </OperatorPageHeader>

    <!-- No celular a região rola; na mesa a grade enche a altura e rola por dentro. -->
    <section
      class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-3 pt-3 pb-3 md:overflow-hidden md:px-4 md:pt-2.5 md:pb-2"
    >
      <OperatorScreenState v-if="pending && !view" state="loading" what="os pedidos desta estação" />
      <!-- Estação que não existe mais (404): não é falha de conexão, e o board em
           cache seria de uma estação que sumiu. Diz o que houve e leva à lista. -->
      <OperatorScreenState
        v-else-if="notHere"
        state="empty"
        icon="i-lucide-map-pin-off"
        title="Esta estação não existe mais"
        description="Escolha a estação deste dispositivo na lista."
      >
        <template #actions>
          <NuxtButton to="/" color="neutral" variant="outline" icon="i-lucide-list" label="Ver estações" />
        </template>
      </OperatorScreenState>
      <OperatorScreenState
        v-else-if="error && !view"
        state="error"
        what="os pedidos desta estação"
        @retry="refresh()"
      />
      <!-- Erro com dados em cache NUNCA apaga o board: um blip de 1 poll não pode
           esconder os tickets da cozinha. O aviso em cima, os cards embaixo. -->
      <OperatorScreenState v-else-if="error && view" state="offline" :since="lastRead" />

      <template v-if="view && !notHere">
        <!-- A FAZER: o que falta somando a fila INTEIRA (inclusive o "+N"), numa linha,
             sem chip cortado na borda. Só na mesa. -->
        <KdsAllDayStrip v-if="view.allDay.length && deskVariant" class="max-md:hidden" :entries="view.allDay" />

        <!-- vazio: estação zerada, estado calmo (omotenashi) -->
        <OperatorScreenState
          v-if="!view.cards.length"
          state="empty"
          icon="i-lucide-coffee"
          title="Tudo em dia"
          :description="emptyTodayLine"
        >
          <template v-if="!soundAnnounces" #actions>
            <NuxtButton
              color="neutral"
              variant="outline"
              icon="i-lucide-volume-2"
              :label="soundOn && soundBlocked ? 'Ativar o som' : 'Ligar o som nos Ajustes'"
              @click="handleSoundAction"
            />
          </template>
        </OperatorScreenState>

        <!-- busca ou recorte sem resultado -->
        <OperatorScreenState
          v-else-if="!filteredCards.length"
          state="empty"
          icon="i-lucide-search-x"
          :title="query.trim() ? `Nenhum pedido para “${query.trim()}”.` : 'Nenhum pedido neste recorte.'"
        >
          <template #actions>
            <NuxtButton color="neutral" variant="outline" label="Limpar busca e recorte" @click="clearSearchAndFilter" />
          </template>
        </OperatorScreenState>

        <template v-else>
          <!-- celular: um ticket em foco + a fila em linhas -->
          <KdsPhoneQueue
            v-if="phoneVariant"
            class="md:hidden"
            :cards="filteredCards"
            :focus-pk="phoneFocus?.pk ?? null"
            :next-pk="query ? null : view.nextPk"
            :blocked-refs="view.blockedRefs"
            :addition-pks="view.additionPks"
            :finishing-pks="view.finishingPks"
            :finish-until="finishUntil"
            :all-day="view.allDay"
            :density="density"
            :push-on="push.active.value"
            @choose="(pk) => (chosenPk = pk)"
            @open="(pk) => (openTicketPk = pk)"
            @undo="(pk) => undoFinish(pk)"
            @finish="(pk) => finish(pk)"
            @hold="onHold"
          />

          <!-- tablet e desktop: a fila em foco -->
          <div v-if="deskVariant" class="flex min-h-0 flex-1 flex-col gap-2 max-md:hidden">
            <div ref="gridBox" class="min-h-0 flex-1 overflow-y-auto" data-kds-grid-box>
              <TransitionGroup tag="div" name="kds-card" class="grid gap-2.5" :style="gridStyle" data-kds-grid>
                <div
                  v-for="card in slice.visible"
                  :key="card.pk"
                  class="flex self-start"
                  :style="placementStyle(card.pk)"
                  data-kds-grid-cell
                >
                  <KdsTicketCard
                    :ticket="card"
                    :density="density"
                    :eyebrow="positions.get(card.pk) ?? ''"
                    :next="!query && filter === 'all' && card.pk === view.nextPk"
                    :blocked="view.blockedRefs.has(card.order_ref)"
                    :addition="view.additionPks.has(card.pk)"
                    :finishing="view.finishingPks.has(card.pk)"
                    :finish-until="finishUntil.get(card.pk)"
                    @open="openTicketPk = card.pk"
                    @start="start(card.pk)"
                    @finish="finish(card.pk)"
                    @undo="undoFinish(card.pk)"
                    @blocked="warnBlocked"
                    @locked="warnLocked(card.pk)"
                  />
                </div>
              </TransitionGroup>
            </div>
            <!-- o excedente: número e agregado, nunca card minúsculo nem paginação -->
            <NuxtButton
              v-if="slice.rest.length"
              color="neutral"
              variant="outline"
              block
              class="shrink-0 justify-center whitespace-normal text-center"
              data-kds-rest
              @click="expanded = true"
            >
              <span>
                <b class="tabular-nums text-highlighted">{{ rest.count }}</b>
                · {{ rest.detail }} ·
                <span class="font-semibold text-highlighted underline underline-offset-2">Ver a fila inteira</span>
              </span>
            </NuxtButton>
            <NuxtButton
              v-else-if="expanded"
              color="neutral"
              variant="outline"
              block
              class="shrink-0 justify-center"
              label="Voltar à fila em foco"
              data-kds-rest-collapse
              @click="expanded = false"
            />
          </div>
        </template>
      </template>
    </section>

    <!-- celular: o ato do ticket em foco, na base, entre a fila e a barra inferior -->
    <div v-if="phoneVariant && phoneAction && view && !notHere" class="contents md:hidden">
      <OperatorActionBar
        :action="phoneAction"
        :context-label="phoneContext.label"
        :context-value="phoneContext.value"
        label="Ato do pedido em foco"
      />
    </div>

    <!-- detalhe (aberto pelo card ou pelo toque longo) -->
    <KdsTicketModal
      :open="openTicket != null"
      :ticket="openTicket"
      :volumes-busy="volumesBusy"
      @update:open="setModalOpen"
      @volumes="onVolumes"
    />

    <!-- toque longo no celular: ver o pedido, desfazer, reabrir -->
    <KdsHoldSheet
      v-model:open="holdOpen"
      :ticket="heldTicket"
      :finishing="heldTicket ? view?.finishingPks.has(heldTicket.pk) ?? false : false"
      :recent-count="view?.recentDone.length ?? 0"
      @view="heldTicket && (openTicketPk = heldTicket.pk)"
      @undo="heldTicket && undoFinish(heldTicket.pk)"
      @reopen="recallOpen = true"
    />

    <!-- recall: concluídos recentes (desfazer o Pronto) -->
    <NuxtModal
      v-model:open="recallOpen"
      title="Concluídos recentes"
      description="Reabra um pedido marcado Pronto por engano (últimos 30 minutos)."
    >
      <template #body>
        <OperatorScreenState
          v-if="!view || !view.recentDone.length"
          state="empty"
          in-card
          icon="i-lucide-rotate-ccw"
          title="Nada concluído nos últimos 30 minutos."
        />
        <ul v-else class="flex flex-col gap-1.5" data-kds-recall-list>
          <li
            v-for="t in view.recentDone"
            :key="t.pk"
            class="flex items-center gap-3 rounded-lg border border-default p-3"
          >
            <div class="min-w-0 flex-1">
              <p class="text-lg font-bold tabular-nums leading-tight">
                {{ splitRef(t.order_ref).code }}
              </p>
              <p class="break-words op-label text-muted-foreground">
                {{ t.customer_name || t.order_ref
                }}<template v-if="t.completed_at_display"> · {{ t.completed_at_display }}</template>
              </p>
            </div>
            <NuxtButton
              v-if="t.volumes_order_ref"
              color="neutral"
              variant="outline"
              icon="i-lucide-package"
              :label="t.volumes ? `${t.volumes} volumes` : 'Volumes'"
              :aria-label="`Volumes do pedido ${splitRef(t.order_ref).code}`"
              data-kds-recent-volumes
              @click="openFromRecent(t.pk)"
            />
            <NuxtButton
              color="neutral"
              variant="outline"
              icon="i-lucide-rotate-ccw"
              label="Reabrir"
              :aria-label="`Reabrir o pedido ${splitRef(t.order_ref).code}`"
              @click="recall(t.pk)"
            />
          </li>
        </ul>
      </template>
    </NuxtModal>
  </main>
</template>

<style scoped>
/* Transição da grade: no Pronto, o card sai com um respiro e a fila desliza (FLIP),
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

@media (prefers-reduced-motion: reduce) {
  .kds-card-move,
  .kds-card-enter-active,
  .kds-card-leave-active {
    transition: none;
  }
}
</style>
