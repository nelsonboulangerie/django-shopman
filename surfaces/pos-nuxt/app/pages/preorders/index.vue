<script setup lang="ts">
// ENCOMENDAS: a agenda do balcão, numa tela só (redesenho aprovado pelo dono,
// 28/09/2026; a tela da seção do brief de 02/10). Chega-se aqui pela barra lateral.
//
// Fase 2 (WP-FASE2-UX-OPERADOR): cada coisa no papel da sua barra, sem barra própria.
//
//   Barra primária      o título; a BUSCA da tela, que é o "Cliente veio buscar"
//                       (a busca da suíte com o alcance "Esta tela", no `/`): nome,
//                       telefone, CPF/CNPJ, endereço ou número (inclusive o do
//                       iFood), em aberto de QUALQUER data; um resultado só, Enter
//                       abre. Leitor de código com o foco fora de campo abre a
//                       busca já com a leitura. A ação primária (Nova encomenda;
//                       no celular o kit a desce para a linha de baixo da barra)
//                       e, no ⋯, o lote das Vias Pedido e Atualizar.
//   Toolbar             à esquerda, os recortes de todo dia (A receber, Sem Via
//                       Pedido, Retiradas, Entregas) num toque e com a contagem: a
//                       faixa de filtros rápidos da suíte (`OperatorQuickFilters`,
//                       decisão do dono, P1 de 02/10), com os favoritos fixados no
//                       fim. Depois o Período do kit (dia, semana, mês, próximos e
//                       últimos dias, personalizado; ‹ › e a data) e o painel de
//                       filtros único da suíte (`OperatorFilterPanel`): o resto mora
//                       nos filtros completos, e os favoritos são do balcão
//                       (`pos`/`preorders`). No celular (filtro único da suíte, dono
//                       04/11/2026) os recortes de todo dia são os filtros rápidos do
//                       painel, aberto pelo ícone da linha do chão, e o Período fica
//                       numa faixa logo abaixo. Na mesa, grade ou lista e, no fim, a
//                       leitura: "Hoje" (o que falta para o dia, sempre de hoje) e o
//                       resumo do período. Durante a busca os recortes e o Período
//                       saem (a busca não tem período) e entra "Incluir concluídas".
//   Aviso da tela       o pagamento a conferir, com o gesto de ver só elas.
//   Cards               a semana (dias lado a lado, ou um embaixo do outro) ou o
//                       dia por janela, em grade ou lista. Na semana o card se
//                       ARRASTA para outro dia: é reagendar (a rota do Reagendar do
//                       detalhe, com a pergunta do kit e o aviso ao cliente). O ⋯
//                       "Mudar de dia" do card é o mesmo gesto por teclado e toque.
//   Ação na base        no celular, "Ler código da encomenda" (`OperatorActionBar`).
//
// O estado inteiro mora na URL (`presentation/preorders.parseView`): a volta do
// detalhe cai no mesmo lugar, e o kiosk guarda o favorito.
//
// Hidratação: as leituras são do cliente (`server: false`). Sem lista e sem erro a
// tela é "carregando" nos DOIS lados (servidor e primeiro desenho do cliente), nunca
// "carregando" só onde o `pending` já virou: era o mismatch de `/preorders`.
import { useEventListener, watchDebounced } from "@vueuse/core";

import { batchNotice, canPrintBatch, isoDate, printCtaLabel } from "~/presentation/orderTickets";
import { preorderDetailPath } from "~/presentation/preorderDetail";
import { NEW_ORDER_ROUTE } from "~/presentation/orderSetup";
import {
  LAYOUT_OPTIONS,
  LAYOUT_STORAGE_KEY,
  PREORDERS_MAX_SPAN_DAYS,
  PREORDERS_PERIOD_PRESETS,
  PREORDERS_SCOPE_NOTE,
  SEARCH_LABEL,
  SEARCH_MIN_CHARS,
  SEARCH_PLACEHOLDER,
  TO_RECEIVE_CLASS,
  canDropOn,
  canMoveCard,
  canSearch,
  checkCount,
  checkPaymentNotice,
  dayColumnTitle,
  dayOpen,
  flipDay,
  todayIndicators,
  NO_FILTERS,
  dayToReceiveLine,
  filterDays,
  filterDimensions,
  filterEmptyMessage,
  flattenDays,
  filtersFromQuickKeys,
  fromActiveFilters,
  fromPanelFilters,
  groupByWindow,
  hasFilters,
  listSummary,
  moveTargets,
  parseLayout,
  parseView,
  periodEmptyMessage,
  periodIsToday,
  periodParams,
  periodSelectionOf,
  periodSummaryLabel,
  preorderCountLabel,
  printPlan,
  QUICK_FILTERS,
  quickFilterItems,
  quickKeysOf,
  searchCompletedHeading,
  searchEmptyMessage,
  searchLimitNote,
  searchOpenEmptyMessage,
  searchOpenHeading,
  singleResult,
  toActiveFilters,
  toReceiveLine,
  todayFacts,
  todayOf,
  viewOfPeriod,
  viewPath,
  viewQuery,
  type PreorderFilters,
  type PreordersLayout,
  type PreordersView,
} from "~/presentation/preorders";
import type { PeriodSelection } from "../../../../operator-kit/app/presentation/dates";
import { periodLabel, resolvePeriod } from "../../../../operator-kit/app/presentation/dates";
import { filterBarActiveFilters } from "../../../../operator-kit/app/presentation/filterBar";
import type { FilterPanelQuery } from "../../../../operator-kit/app/presentation/filterPanel";
import type { OperatorHeaderAction } from "../../../../operator-kit/app/presentation/pageHeader";
import type { OperatorScreenAlert } from "../../../../operator-kit/app/presentation/screenState";
import type { ActiveFilters } from "../../../../operator-kit/app/types/filters";
import type { PreorderCard, PreorderDay } from "~/types/preorders";

useHead({ title: "Encomendas" });

const { pos, pending: posPending, refresh: refreshPos } = await usePosTerminal();

const route = useRoute();
const router = useRouter();
// HOJE é o dia da LOJA, nunca o relógio deste dispositivo: um tablet com a data ou o
// fuso errado abria as Encomendas no dia errado e chamava de "Hoje" o dia de ontem. O
// servidor diz o dia dele em dois lugares, os dois `timezone.localdate()`: na lista
// (`list.today`, contrato `PreorderList.today` em `projections/preorders.py`) e no
// terminal (`pos.delivery_today`). A lista depende do recorte, e o recorte parte de
// hoje: o primeiro desenho lê o terminal (já carregado, `await` acima); a lista, quando
// chega, confirma. O relógio do dispositivo só entra se o servidor não disse nada.
const deviceToday = isoDate(new Date());
const today = computed(() => pos.value?.delivery_today || deviceToday);
const view = computed(() => parseView(route.query, today.value));

function update(patch: Partial<PreordersView>) {
  void router.replace({ path: "/preorders", query: viewQuery({ ...view.value, ...patch }, today.value) });
}

// O recorte de agora: cada linha o leva ao detalhe (`?back=`), e a volta cai nele.
const back = computed(() => viewPath(view.value, today.value));

// ── O período (Dia ou Semana) ──
const params = computed(() => periodParams(view.value));
const period = usePosPreorders(params);
const list = computed(() => period.list.value ?? null);
const filters = computed<PreorderFilters>({
  get: () => ({ fulfillment: view.value.fulfillment, pay: view.value.pay, print: view.value.print }),
  set: (next) => update(next),
});
const allCards = computed(() => flattenDays(list.value?.days ?? []));
const days = computed<PreorderDay[]>(() => filterDays(list.value?.days ?? [], filters.value));
const shownCount = computed(() => flattenDays(days.value).length);
const day = computed(() => days.value[0] ?? null);
const summary = computed(() => (list.value ? listSummary(list.value.count, list.value.total_display) : ""));
const toReceive = computed(() => (list.value && list.value.count
  ? toReceiveLine(list.value.to_receive_q, list.value.to_receive_display)
  : ""));
// O resumo do período some quando o período é só hoje: a linha "Hoje" já diz.
const showSummary = computed(() => !!summary.value && !periodIsToday(view.value, today.value));

// ── Hoje: do período, quando ele contém hoje; senão, da leitura do selo da barra ──
const ahead = usePosPreordersAhead();
const todayLine = computed(() => todayFacts(todayOf(list.value, ahead.value)));
// O "Período" do kit (Tipo 2): ‹ › andam um período igual ao escolhido, e o
// estado continua na URL (modo + data, e o fim no personalizado).
const periodSelection = computed<PeriodSelection>({
  get: () => periodSelectionOf(view.value, today.value),
  set: (next) => update(viewOfPeriod(next, today.value)),
});

// ── Os filtros: o painel único da suíte ──
const dimensions = computed(() => filterDimensions(allCards.value, filters.value));
const activePanel = computed<ActiveFilters>({
  get: () => toActiveFilters(filters.value),
  set: (next) => { filters.value = fromPanelFilters(filters.value, next); },
});
// Os recortes de todo dia: um toque, com a contagem (a faixa de filtros rápidos).
const quickItems = computed(() => quickFilterItems(allCards.value, filters.value));
const quickModel = computed<string[]>({
  get: () => quickKeysOf(filters.value),
  set: (keys) => { filters.value = filtersFromQuickKeys(filters.value, keys); },
});
const panelQuery = computed<FilterPanelQuery>(() => ({ filters: activePanel.value }));
// O favorito fixado aplica o recorte inteiro dele (não soma no que está).
function applyFavorite(query: FilterPanelQuery) {
  filters.value = fromActiveFilters(query.filters ?? {});
}
const activeFilters = computed(() => filterBarActiveFilters(dimensions.value, activePanel.value, (next) => {
  activePanel.value = next;
}));

// Pagamento a conferir não é opção escondida: é aviso da tela, com o gesto de ver só
// elas. Ligado o recorte, o aviso sai: o chip "Pagamento: A conferir" diz o que se
// vê, e o X dele é o único jeito de voltar.
const checkNotice = computed(() => checkPaymentNotice(checkCount(allCards.value, filters.value)));
const alerts = computed<OperatorScreenAlert[]>(() => (!searching.value && checkNotice.value && filters.value.pay !== "check"
  ? [{
      id: "check-payment",
      title: checkNotice.value,
      color: "warning",
      icon: "i-lucide-circle-help",
      action: { label: "Mostrar só essas", onSelect: () => { filters.value = { ...filters.value, pay: "check" }; } },
    }]
  : []));

// ── O lote: do que está visível, só as vias que faltam ──
const tickets = usePosOrderTickets(pos);
const plan = computed(() => (list.value ? printPlan(list.value, days.value) : null));
const printCount = computed(() => plan.value?.refs.length ?? 0);
const maxBatch = computed(() => list.value?.max_batch ?? 0);
const notice = computed(() => batchNotice(printCount.value, maxBatch.value));

async function printMissing() {
  if (plan.value && (await tickets.printBatch(plan.value))) await period.refresh();
}

// O ⋯ da mesa: o lote das Vias Pedido do que se vê (Atualizar entra no fim, pela
// moldura). Desligado, diz por quê.
const printAction = computed<OperatorHeaderAction | null>(() => {
  if (searching.value || !list.value?.count) return null;
  const noPrinter = !tickets.hasPrinter.value
    ? `${tickets.printerUnavailableReason.value} A Via Pedido sai no balcão que tem impressora.`
    : "";
  const blocked = !canPrintBatch(printCount.value, maxBatch.value);
  return {
    label: printCtaLabel(printCount.value, shownCount.value),
    icon: "i-lucide-printer",
    disabled: blocked || tickets.printing.value || !!noPrinter,
    reason: noPrinter || (notice.value?.tone === "danger" ? notice.value.message : ""),
    onSelect: () => void printMissing(),
  };
});
const deskActions = computed<OperatorHeaderAction[]>(() => (printAction.value ? [printAction.value] : []));
function openDay(date: string) {
  update({ mode: "day", date });
}
// Os dias recolhidos na grade: hoje nasce aberto, o resto só abre no toque (dono,
// 03/11/2026). A escolha vive enquanto o PDV está aberto, inclusive na volta do detalhe.
const flippedDayList = useState<string[]>("pos-preorders-flipped-days", () => []);
const flippedDays = computed(() => new Set(flippedDayList.value));
function toggleDay(date: string) {
  flippedDayList.value = [...flipDay(flippedDays.value, date)];
}
// A coluna estreita do dia recolhido: "Qua", e o nome inteiro para o leitor de tela.
const NuxtButtonComponent = resolveComponent("NuxtButton");


function narrowWeekday(day: PreorderDay): string {
  const w = day.weekday_display || "";
  return w.charAt(0).toUpperCase() + w.slice(1);
}
function narrowDayLabel(day: PreorderDay): string {
  const parts = [dayColumnTitle(day), day.orders_count ? `${preorderCountLabel(day.orders_count)}, ${day.total_display}` : "Nenhuma encomenda"];
  const receive = dayToReceiveLine(day);
  if (receive) parts.push(receive);
  return day.orders.length ? `${parts.join(". ")}. Abrir o dia.` : `${parts.join(". ")}.`;
}

// ── Cliente veio buscar: a busca da tela ──
const typed = ref(view.value.q);
watchDebounced(typed, (value) => {
  if (value.trim() !== view.value.q) update({ q: value.trim() });
}, { debounce: 250 });
// A URL muda por fora (voltar do detalhe, favorito): o campo acompanha.
watch(() => view.value.q, (value) => { if (value !== typed.value.trim()) typed.value = value; });

const query = computed(() => view.value.q);
const includeCompleted = computed({
  get: () => view.value.completed,
  set: (value: boolean) => update({ completed: value }),
});
const searching = computed(() => typed.value.trim().length > 0);
const enabled = computed(() => canSearch(query.value));
const search = usePosPreorderSearch({ query, includeCompleted, enabled });
const result = computed(() => search.result.value ?? null);
const resultCount = computed(() => (result.value ? result.value.open_count + result.value.completed_count : null));
const openLimit = computed(() => (result.value ? searchLimitNote(result.value.open.length, result.value.open_count) : ""));
const completedLimit = computed(() => (result.value
  ? searchLimitNote(result.value.completed.length, result.value.completed_count)
  : ""));
const nothingAnywhere = computed(() => !!result.value && result.value.include_completed
  && !result.value.open_count && !result.value.completed_count);

const searchBox = useTemplateRef<{ open: () => void }>("searchBox");

function openSingle() {
  const only = singleResult(result.value);
  if (only) void navigateTo(preorderDetailPath(only.ref, back.value));
}

// Leitor de código (ou alguém digitando) com o foco fora de qualquer campo: a
// primeira tecla abre a busca da tela com ela, e o resto da leitura cai no campo.
// Enter com a busca feita e um resultado só abre o detalhe.
let typedAt = 0;
useEventListener(typeof window === "undefined" ? null : window, "keydown", (event: KeyboardEvent) => {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const target = event.target instanceof Element ? event.target : null;
  if (target?.closest("input, textarea, select, button, a, [contenteditable='true'], [role='dialog']")) return;
  if (event.key === "Enter") {
    if (searching.value) openSingle();
    return;
  }
  if (event.key.length !== 1 || event.key === "/") return;
  event.preventDefault();
  const now = Date.now();
  typed.value = now - typedAt < 500 ? typed.value + event.key : event.key;
  typedAt = now;
  searchBox.value?.open();
});

// ── Grade ou lista: preferência deste dispositivo (como a densidade da grade de
//    produtos do balcão). O servidor desenha a grade; a escolha guardada entra
//    depois de montar, para a hidratação não divergir. ──
const layout = ref<PreordersLayout>("grid");
onMounted(() => {
  try {
    layout.value = parseLayout(localStorage.getItem(LAYOUT_STORAGE_KEY));
  } catch {
    // Armazenamento bloqueado (janela anônima, quiosque): fica a grade.
  }
});
function setLayout(value: PreordersLayout) {
  layout.value = value;
  try {
    localStorage.setItem(LAYOUT_STORAGE_KEY, value);
  } catch {
    // Sem armazenamento a escolha vale até sair da tela.
  }
}
const asGrid = computed(() => layout.value === "grid");
// Cards em colunas (grade) ou a linha inteira de cada um (lista).
const cardsClass = computed(() => (asGrid.value
  ? "grid grid-cols-[repeat(auto-fill,minmax(min(18rem,100%),1fr))] items-start gap-2"
  : "grid gap-2"));

// ── Mudar de dia: arrastar o card na semana, ou o menu do card ──
// O hoje da LOJA que a lista confirmou (`list.today`): é ele que decide se um dia já
// passou ao mover um card.
const storeToday = computed(() => list.value?.today || today.value);
const move = usePosPreorderMove({ pos, today: storeToday, refresh: () => period.refresh() });
const dragging = ref<PreorderCard | null>(null);
const dropDate = ref("");
// Em qualquer período de vários dias (semana, mês, próximos dias…) o card se
// arrasta entre os dias da tela; no Dia só há um dia, e o menu leva ao Reagendar.
const multiDay = computed(() => view.value.mode !== "day");

function movable(card: PreorderCard): boolean {
  return multiDay.value && canMoveCard(card) && !move.busy.value;
}

function targetsFor(card: PreorderCard) {
  return moveTargets(list.value?.days ?? [], card, storeToday.value);
}

function onDragStart(event: DragEvent, card: PreorderCard) {
  dragging.value = card;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", card.ref);
  }
}

function onDragOver(event: DragEvent, date: string) {
  if (!dragging.value || !canDropOn(date, dragging.value, storeToday.value)) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  dropDate.value = date;
}

function onDragLeave(event: DragEvent, date: string) {
  const zone = event.currentTarget as HTMLElement | null;
  if (zone?.contains(event.relatedTarget as Node | null)) return;
  if (dropDate.value === date) dropDate.value = "";
}

function endDrag() {
  dragging.value = null;
  dropDate.value = "";
}

function onDrop(date: string) {
  const card = dragging.value;
  endDrag();
  if (card && canDropOn(date, card, storeToday.value)) void move.moveTo(card, date);
}

/** O dia como alvo do arrasto: onde se pode soltar ganha contorno; o de baixo do card, destaque. */
function dropClass(date: string): string {
  if (!dragging.value) return "";
  if (dropDate.value === date) return "ring-2 ring-primary";
  return canDropOn(date, dragging.value, storeToday.value) ? "ring-1 ring-primary/50" : "opacity-60";
}

// ── CELULAR: a tela abre no DIA de hoje (v3 celular: "lista de hoje"), salvo quando
//    a URL já diz outro recorte (volta do detalhe, favorito). Comportamento, depois
//    de montar: a árvore do primeiro desenho é a mesma no servidor e no cliente. ──
onMounted(() => {
  if (window.matchMedia("(max-width: 767.98px)").matches && !route.query.mode && !route.query.date && !route.query.q) {
    update({ mode: "day", date: storeToday.value });
  }
});

// O QR da mensagem que o cliente recebeu traz o número da encomenda: a leitura
// vira a busca, e um resultado só abre o detalhe.
const scannerOpen = ref(false);
const scannedPending = ref(false);
function onScannedOrder(code: string) {
  scannedPending.value = true;
  const ref = code.trim().split(/[/?#=]/).filter(Boolean).pop() || code.trim();
  typed.value = ref;
  update({ q: ref });
}
watch(result, (value) => {
  // Leitura pelo QR: só abre sozinha quando a busca veio do leitor.
  if (value && typed.value && singleResult(value) && scannedPending.value) {
    scannedPending.value = false;
    openSingle();
  }
});

// ── A linha do chão no celular (modelo de navegação, 31/10/2026) ──
// O cabeçalho vira uma linha: período, recortes e o painel moram no Filtros dela, e o
// recorte ativo fica nomeado na faixa logo abaixo, com a contagem e o Limpar. "Hoje"
// segue à vista numa linha própria: é a leitura do caixa, e esconder no ⋮ esconderia o
// que falta receber.
const compactPeriodOff = computed(() => !periodIsToday(view.value, today.value));
const compactFilterActive = computed(() => !searching.value && (compactPeriodOff.value || activeFilters.value.length > 0));
const compactFilterLabel = computed(() => [
  compactPeriodOff.value
    ? periodLabel(periodSelection.value, resolvePeriod(periodSelection.value, { today: today.value }), today.value).replace(" · ", ", ")
    : "",
  ...activeFilters.value.map((filter) => filter.label),
].filter(Boolean).join(", "));
const compactSummary = computed(() => {
  if (searching.value) {
    if (resultCount.value == null) return "";
    return resultCount.value === 1 ? "1 encontrada." : `${resultCount.value} encontradas.`;
  }
  return shownCount.value === 1 ? "1 encomenda." : `${shownCount.value} encomendas.`;
});
const compactOptions = computed<OperatorHeaderAction[]>(() => [
  { label: "Nova encomenda", icon: "i-lucide-plus", onSelect: () => void navigateTo(NEW_ORDER_ROUTE) },
  ...deskActions.value,
]);
// Limpar volta à chegada da tela: sem busca, sem recortes, no dia de hoje.
// O atalho do indicador de Hoje: o dia de hoje, com o recorte do fato (A Receber, Sem
// Via, Conferir). Limpar volta a tudo.
function applyTodayFilter(filter: Partial<PreorderFilters>) {
  typed.value = "";
  update({ ...NO_FILTERS, ...filter, q: "", mode: "day", date: today.value, to: "" });
}
function compactClear() {
  typed.value = "";
  update({ ...fromActiveFilters({}), q: "", mode: "day", date: today.value, to: "" });
}
const compactPhone = useScreen().belowMd;

function refreshAll() {
  void refreshPos();
  void period.refresh();
  if (enabled.value) void search.refresh();
}
</script>

<template>
  <PosPreordersShell
    :pos="pos"
    :pending="posPending || period.pending.value || search.pending.value"
    wide
    :actions="deskActions"
    :alerts="alerts"
    :active-filters="searching ? [] : activeFilters"
    :compact-query="typed"
    :compact-filter-active="compactFilterActive"
    :compact-filter-label="compactFilterLabel"
    :compact-summary="compactSummary"
    :compact-options="compactOptions"
    @refresh="refreshAll"
    @compact-clear="compactClear"
  >
    <!-- O filtro único da suíte no celular (dono, 04/11/2026): o ícone na linha do chão,
         antes da busca, com o número no canto, como o sino. Na mesa os recortes de todo
         dia têm a faixa de um toque; aqui eles são os filtros rápidos do painel. -->
    <template v-if="!searching && list && list.count" #compact-filter-panel>
      <OperatorFilterPanel
        v-model="activePanel"
        :dimensions="dimensions"
        :quick="[...QUICK_FILTERS]"
        trigger="icon"
        :chips="false"
        surface="pos"
        screen="preorders"
        data-compact-panel
      />
    </template>
    <!-- O período (que dia é a tela) segue à vista no celular, logo abaixo da linha; na
         busca, "Incluir concluídas" toma o lugar dele. -->
    <template #compact-primary>
      <OperatorPeriodPicker
        v-if="!searching"
        v-model="periodSelection"
        compact
        :presets="PREORDERS_PERIOD_PRESETS"
        custom
        :max-span-days="PREORDERS_MAX_SPAN_DAYS"
        :today="today"
        label="Período das encomendas"
        data-compact-period
      />
      <NuxtSwitch v-else v-model="includeCompleted" label="Incluir concluídas" />
    </template>
    <!-- HOJE no celular (dono, 03/11/2026: "só indicadores, e o toque mostra mais"): uma
         faixa branca, como a linha do chão. Cada fato é um indicador com ícone, valor e
         uma legenda curta (lê-se sem tocar); o que pede gesto é atalho para o recorte
         dele (A Receber, Sem Via, Conferir), e a seta abre as frases inteiras. -->
    <template v-if="!searching && todayLine.length" #compact-below>
      <div class="flex items-stretch border-b border-default bg-card md:hidden" role="group" aria-label="Hoje" data-compact-today>
        <span class="flex items-center px-3 text-sm font-semibold text-primary">Hoje</span>
        <component
          :is="indicator.filter ? 'button' : 'span'"
          v-for="indicator in todayIndicators(todayLine)"
          :key="indicator.key"
          v-bind="indicator.filter ? { type: 'button' } : {}"
          class="flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center px-1 py-1 leading-none tabular-nums"
          :class="[
            indicator.urgent
              ? (indicator.key === 'check' ? 'text-warning' : 'text-highlighted')
              : 'text-muted',
            indicator.filter ? 'hover:bg-elevated active:bg-elevated' : '',
          ]"
          :aria-label="indicator.filter ? `${indicator.text}. Mostrar só essas.` : indicator.text"
          :data-compact-today-indicator="indicator.key"
          @click="indicator.filter ? applyTodayFilter(indicator.filter) : undefined"
        >
          <span class="inline-flex items-center gap-1 text-sm" :class="indicator.urgent ? 'font-semibold' : ''">
            <NuxtIcon :name="indicator.icon" class="size-4 shrink-0" aria-hidden="true" />{{ indicator.value }}
          </span>
          <span class="mt-0.5 op-micro text-muted" aria-hidden="true">{{ indicator.caption }}</span>
        </component>
        <NuxtPopover :content="{ align: 'end', sideOffset: 4 }">
          <NuxtButton
            color="neutral"
            variant="ghost"
            square
            icon="i-lucide-chevron-down"
            class="size-11 shrink-0 justify-center self-center"
            aria-label="Hoje: ver as frases inteiras"
            data-compact-today-more
          />
          <template #content>
            <ul class="grid gap-2 p-3 text-sm" data-compact-today-details>
              <li v-for="indicator in todayIndicators(todayLine)" :key="indicator.key" class="flex items-center gap-2">
                <NuxtIcon :name="indicator.icon" class="size-4 shrink-0 text-muted" aria-hidden="true" />
                <span :class="indicator.urgent ? 'font-semibold text-highlighted' : 'text-muted'">{{ indicator.text }}</span>
              </li>
            </ul>
          </template>
        </NuxtPopover>
      </div>
    </template>
    <!-- A BUSCA DA TELA: "Cliente veio buscar" (o `/` abre; Tab troca para o app e a
         suíte). O que ela acha toma o lugar do período, na própria tela. -->
    <template #search>
      <OperatorSuiteSearch
        ref="searchBox"
        v-model="typed"
        :placeholder="SEARCH_PLACEHOLDER"
        :aria-label="SEARCH_LABEL"
        screen-label="filtrando as encomendas"
        :screen-count="resultCount"
        data-preorders-search
      />
    </template>

    <!-- A AÇÃO PRIMÁRIA: a venda, já no modo Encomendas, numa comanda livre. -->
    <template #primary>
      <NuxtButton
        icon="i-lucide-plus"
        label="Nova encomenda"
        data-preorders-new
        @click="navigateTo(NEW_ORDER_ROUTE)"
      />
    </template>

    <!-- O RECORTE: os recortes de todo dia e o Período (fora da busca), ou "Incluir
         concluídas" (só na busca). -->
    <template #filters-primary>
      <OperatorQuickFilters
        v-if="!searching && list && list.count"
        v-model="quickModel"
        :items="quickItems"
        multiple
        label="Recortes das encomendas"
        surface="pos"
        screen="preorders"
        :query="panelQuery"
        data-preorders-quick
        @apply="applyFavorite"
      />
      <!-- No celular o Período vem primeiro (que dia é a tela) e os recortes rolam
           depois dele; na mesa, recortes à esquerda e o Período depois. -->
      <OperatorPeriodPicker
        v-if="!searching"
        v-model="periodSelection"
        class="min-w-0 max-sm:order-first"
        compact
        :presets="PREORDERS_PERIOD_PRESETS"
        custom
        :max-span-days="PREORDERS_MAX_SPAN_DAYS"
        :today="today"
        label="Período das encomendas"
        data-preorders-period
      />
      <NuxtSwitch
        v-else
        v-model="includeCompleted"
        label="Incluir concluídas"
        data-preorders-include-completed
      />
    </template>

    <template v-if="!searching && list && list.count" #filter-panel>
      <OperatorFilterPanel
        v-model="activePanel"
        :dimensions="dimensions"
        surface="pos"
        screen="preorders"
        data-preorders-filters
      />
    </template>

    <!-- A FORMA da lista (só na mesa): grade ou lista, preferência do dispositivo. -->
    <template #filters>
      <div class="flex items-center gap-1" role="group" aria-label="Arrumação das encomendas" data-preorders-layout>
        <NuxtButton
          v-for="option in LAYOUT_OPTIONS"
          :key="option.value"
          :icon="option.icon"
          color="neutral"
          variant="outline"
          square
          :active="layout === option.value"
          active-color="primary"
          active-variant="solid"
          :aria-label="option.label"
          :title="option.label"
          :aria-pressed="layout === option.value"
          :data-preorders-layout-option="option.value"
          @click="setLayout(option.value)"
        />
      </div>
    </template>

    <!-- A LEITURA, no fim da linha: HOJE (sempre de hoje) e o resumo do PERÍODO na
         tela: o que falta receber primeiro, o total vendido depois e menor
         (grandezas diferentes, nunca somadas). -->
    <template v-if="!searching && (todayLine.length || (list && list.count && showSummary))" #filters-end>
      <div
        class="flex min-w-0 flex-wrap items-baseline gap-x-6 gap-y-1 sm:ms-auto"
        aria-label="Hoje e o resumo do período"
        role="group"
      >
        <p v-if="todayLine.length" class="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm" data-preorders-today>
          <span class="font-semibold text-primary">Hoje</span>
          <span
            v-for="fact in todayLine"
            :key="fact.key"
            :class="fact.key === 'to_receive' && fact.urgent
              ? TO_RECEIVE_CLASS
              : fact.key === 'check' ? 'tabular-nums text-warning' : 'tabular-nums text-muted'"
            :data-preorders-today-fact="fact.key"
          >{{ fact.text }}</span>
        </p>
        <div
          v-if="list && list.count && showSummary"
          class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5"
          data-preorders-summary
        >
          <span class="text-sm font-semibold text-muted">{{ periodSummaryLabel(view.mode, hasFilters(filters)) }}</span>
          <p v-if="toReceive" :class="TO_RECEIVE_CLASS" data-preorders-to-receive>{{ toReceive }}</p>
          <p class="text-xs tabular-nums text-muted" data-preorders-total>{{ summary }}</p>
        </div>
      </div>
    </template>

    <!-- ── O RESULTADO DA BUSCA toma o lugar do período. ── -->
    <template v-if="searching">
      <NuxtAlert
        v-if="!enabled"
        color="info"
        variant="subtle"
        icon="i-lucide-info"
        :title="`Digite pelo menos ${SEARCH_MIN_CHARS} letras ou números para procurar.`"
        data-preorders-hint
      />

      <OperatorScreenState
        v-else-if="search.error.value && !result"
        state="error"
        what="a busca das encomendas"
        :description="`${httpErrorMessage(search.error.value, '')} Confira a conexão e tente de novo.`.trim()"
        data-preorders-search-error
        @retry="search.refresh()"
      />

      <OperatorScreenState
        v-else-if="!result"
        state="loading"
        title="Procurando encomendas"
        data-preorders-search-loading
      />

      <template v-else>
        <OperatorScreenState
          v-if="nothingAnywhere"
          state="empty"
          icon="i-lucide-search-x"
          :title="searchEmptyMessage(query, result.completed_days)"
          data-preorders-empty
        />

        <template v-else>
          <!-- EM ABERTO: de qualquer data. -->
          <section
            v-if="result.open_count"
            class="grid gap-2"
            :class="asGrid ? '' : 'max-w-3xl'"
            data-preorders-results="open"
          >
            <h2 class="text-sm font-semibold text-muted">{{ searchOpenHeading(result.open_count) }}</h2>
            <ul :class="cardsClass">
              <li v-for="card in result.open" :key="card.ref">
                <PosPreorderRow :back="back" :card="card" show-date>
                  <template v-if="canMoveCard(card)" #aside>
                    <PosPreorderMoveMenu
                      :customer-name="card.customer_name"
                      :targets="[]"
                      :busy="move.busy.value || move.loading.value === card.ref"
                      @other="move.chooseOther(card)"
                    />
                  </template>
                </PosPreorderRow>
              </li>
            </ul>
            <p v-if="openLimit" class="text-sm text-muted">{{ openLimit }}</p>
          </section>

          <OperatorScreenState
            v-else
            state="empty"
            icon="i-lucide-search-x"
            :title="searchOpenEmptyMessage(query)"
            data-preorders-open-empty
          >
            <template v-if="!result.include_completed" #actions>
              <NuxtButton
                color="neutral"
                variant="outline"
                label="Procurar nas concluídas"
                data-preorders-offer-completed
                @click="includeCompleted = true"
              />
            </template>
          </OperatorScreenState>

          <!-- CONCLUÍDAS: seção à parte, nunca misturada com as em aberto. -->
          <section
            v-if="result.include_completed"
            class="grid gap-2 border-t border-default pt-4"
            :class="asGrid ? '' : 'max-w-3xl'"
            data-preorders-results="completed"
          >
            <h2 class="text-sm font-semibold text-muted">
              {{ searchCompletedHeading(result.completed_count, result.completed_days) }}
            </h2>
            <ul :class="cardsClass">
              <li v-for="card in result.completed" :key="card.ref">
                <PosPreorderRow :back="back" :card="card" show-date />
              </li>
            </ul>
            <p v-if="completedLimit" class="text-sm text-muted">{{ completedLimit }}</p>
          </section>
        </template>
      </template>
    </template>

    <!-- ── O PERÍODO: o dia, ou a semana de segunda a domingo. ── -->
    <template v-else>
      <OperatorScreenState
        v-if="period.error.value && !list"
        state="error"
        what="as encomendas"
        :description="`${httpErrorMessage(period.error.value, '')} Confira a conexão e tente de novo.`.trim()"
        data-preorders-period-error
        @retry="period.refresh()"
      />

      <!-- Sem lista e sem erro: carregando, no servidor e no cliente (a mesma árvore
           nos dois lados; a leitura é só do cliente). -->
      <OperatorScreenState
        v-else-if="!list"
        state="loading"
        what="as encomendas"
        data-preorders-period-loading
      />

      <template v-else>
        <OperatorScreenState
          v-if="!list.count"
          state="empty"
          icon="i-lucide-calendar-x"
          :title="periodEmptyMessage(view.mode)"
          data-preorders-empty
        />

        <template v-else>
          <OperatorScreenState
            v-if="!shownCount"
            state="empty"
            icon="i-lucide-list-filter"
            :title="filterEmptyMessage(view.mode)"
            data-preorders-filter-empty
          />

          <!-- DIA: por janela; em grade, os cards em colunas; em lista, a linha inteira. -->
          <div v-else-if="view.mode === 'day' && day" class="grid gap-4" :class="asGrid ? '' : 'max-w-4xl'" data-preorders-day>
            <NuxtCard
              v-for="group in groupByWindow(day.orders)"
              :key="group.key"
              as="section"
              variant="outline"
              :ui="{ body: 'grid gap-2 p-3 sm:p-3' }"
              data-preorders-window
            >
              <h3 class="flex items-center gap-2 text-sm font-semibold text-muted">
                <NuxtIcon name="i-lucide-clock-3" class="size-4" aria-hidden="true" />
                {{ group.label }}
              </h3>
              <ul :class="cardsClass">
                <li v-for="card in group.orders" :key="card.ref">
                  <PosPreorderRow :back="back" :card="card">
                    <template v-if="canMoveCard(card)" #aside>
                      <PosPreorderMoveMenu
                        :customer-name="card.customer_name"
                        :targets="targetsFor(card)"
                        :busy="move.busy.value || move.loading.value === card.ref"
                        @move="(date) => move.moveTo(card, date)"
                        @other="move.chooseOther(card)"
                      />
                    </template>
                  </PosPreorderRow>
                </li>
              </ul>
            </NuxtCard>
          </div>

          <!-- Hoje leva a moldura do "próximo" do KDS: borda de 2 px e halo, no dourado
               (dono, 03/11/2026). -->
          <!-- SEMANA: uma única árvore responsiva. Em grade, os dias lado a lado numa
               LINHA SÓ (dono, 03/11/2026): o dia aberto ganha a largura útil e o
               recolhido vira uma coluna estreita (dia, data, a conta e o sinal do que
               falta receber), aberta no toque. Em lista, um embaixo do outro. Cada dia
               é também onde se SOLTA o card arrastado (reagendar). -->
          <div v-else data-week-board>
            <div
              :class="asGrid
                ? 'grid gap-2 md:flex md:items-stretch md:overflow-x-auto md:p-1.5'
                : 'grid max-w-4xl gap-3'"
              :data-week-grid="asGrid ? '' : undefined"
              :data-week-list="asGrid ? undefined : ''"
            >
              <NuxtCard
                v-for="weekDay in days"
                :key="weekDay.date"
                as="section"
                variant="outline"
                class="min-w-0 transition"
                :class="[
                  weekDay.is_today ? 'ring-2 ring-primary shadow-[0_0_0_4px_color-mix(in_oklab,var(--ui-primary)_18%,transparent)]' : '',
                  dropClass(weekDay.date),
                  asGrid ? (dayOpen(weekDay, flippedDays) && weekDay.orders.length ? 'md:min-w-[17rem] md:flex-1' : 'md:w-16 md:shrink-0') : '',
                ]"
                :ui="{ body: asGrid && !(dayOpen(weekDay, flippedDays) && weekDay.orders.length)
                  ? 'flex h-full min-w-0 flex-col p-0 sm:p-0'
                  : 'flex min-w-0 flex-col gap-2 p-3 sm:p-3' }"
                :data-week-day="weekDay.date"
                :data-week-day-narrow="asGrid && !(dayOpen(weekDay, flippedDays) && weekDay.orders.length) ? '' : undefined"
                :data-drop-target="dropDate === weekDay.date ? 'over' : undefined"
                @dragover="onDragOver($event, weekDay.date)"
                @dragleave="onDragLeave($event, weekDay.date)"
                @drop.prevent="onDrop(weekDay.date)"
              >
                <!-- A COLUNA ESTREITA (grade): o dia recolhido, ou sem encomenda. O toque
                     abre o dia com encomenda; o vazio só diz que está vazio. Abaixo de md
                     (a semana não cabe numa linha) a coluna deita e vira uma LINHA fina,
                     um dia embaixo do outro (dono, 03/11/2026). -->
                <component
                  :is="weekDay.orders.length ? NuxtButtonComponent : 'div'"
                  v-if="asGrid && !(dayOpen(weekDay, flippedDays) && weekDay.orders.length)"
                  v-bind="weekDay.orders.length
                    ? { color: 'neutral', variant: 'ghost', block: true, 'aria-expanded': false }
                    : { role: 'group' }"
                  class="flex h-full min-h-11 flex-row items-center justify-start gap-2 rounded-[inherit] px-3 py-2 text-left md:min-h-40 md:flex-col md:gap-1.5 md:px-1 md:py-3 md:text-center"
                  :class="weekDay.is_today ? 'bg-primary/10' : ''"
                  :aria-label="narrowDayLabel(weekDay)"
                  :aria-current="weekDay.is_today ? 'date' : undefined"
                  data-week-day-toggle
                  @click="weekDay.orders.length ? toggleDay(weekDay.date) : undefined"
                >
                  <span class="text-xs font-semibold" :class="weekDay.is_today ? 'text-primary' : 'text-highlighted'" aria-hidden="true">
                    {{ weekDay.is_today ? "Hoje" : narrowWeekday(weekDay) }}
                  </span>
                  <span class="text-xs tabular-nums text-muted" aria-hidden="true">{{ weekDay.day_display }}</span>
                  <!-- Deitada (celular), a linha tem espaço para a conta por extenso. -->
                  <span class="min-w-0 truncate text-xs tabular-nums text-muted md:hidden" aria-hidden="true">
                    {{ weekDay.orders_count ? `${preorderCountLabel(weekDay.orders_count)} · ${weekDay.total_display}` : "Nenhuma encomenda" }}
                  </span>
                  <OperatorCountChip
                    v-if="weekDay.orders_count"
                    :count="weekDay.orders_count"
                    aria-hidden="true"
                    data-week-day-count
                  />
                  <NuxtIcon
                    v-if="weekDay.to_receive_q > 0"
                    name="i-lucide-hand-coins"
                    class="size-4 text-warning"
                    aria-hidden="true"
                    data-week-day-to-receive-sign
                  />
                  <NuxtIcon v-if="weekDay.orders.length" name="i-lucide-chevron-right" class="ms-auto size-4 text-muted md:ms-0 md:mt-auto" aria-hidden="true" />
                </component>
                <template v-else>
                <!-- Hoje: o cabeçalho ganha fundo da cor primária e diz "Hoje, ter 29/09";
                     o dia da semana nunca some. Na lista, o cabeçalho é uma linha só.
                     O toque no cabeçalho ABRE ou RECOLHE o dia (dono, 03/11/2026: só
                     hoje nasce aberto); "Ver só este dia" leva ao modo Dia. -->
                <!-- O CABEÇALHO DO DIA ABERTO (versão 1, dono, 03/11/2026): uma linha, sem
                     bloco de destaque; o título (hoje na cor primária), a conta e o que
                     falta receber à esquerda, a seta de recolher à direita. O cabeçalho
                     inteiro recolhe no toque; "Ver só este dia" mora no pé do dia. -->
                <NuxtButton
                  color="neutral"
                  variant="ghost"
                  block
                  class="flex min-w-0 items-start justify-between gap-2 text-left"
                  :aria-expanded="weekDay.orders.length ? dayOpen(weekDay, flippedDays) : undefined"
                  :aria-label="weekDay.orders.length
                    ? `${dayOpen(weekDay, flippedDays) ? 'Recolher' : 'Abrir'} ${dayColumnTitle(weekDay)}`
                    : dayColumnTitle(weekDay)"
                  :aria-current="weekDay.is_today ? 'date' : undefined"
                  data-week-day-toggle
                  :data-week-day-expanded="dayOpen(weekDay, flippedDays) ? '' : undefined"
                  @click="toggleDay(weekDay.date)"
                >
                  <span class="grid min-w-0 gap-1">
                    <span class="text-sm font-semibold" :class="weekDay.is_today ? 'text-primary' : 'text-highlighted'" data-week-day-title>
                      {{ dayColumnTitle(weekDay) }}
                    </span>
                    <span class="text-xs font-normal tabular-nums text-muted" data-week-day-total>
                      <template v-if="weekDay.orders_count">{{ preorderCountLabel(weekDay.orders_count) }} · {{ weekDay.total_display }}</template>
                      <template v-else>Nenhuma encomenda</template>
                    </span>
                    <span v-if="dayToReceiveLine(weekDay)" :class="TO_RECEIVE_CLASS" data-week-day-to-receive>
                      {{ dayToReceiveLine(weekDay) }}
                    </span>
                  </span>
                  <!-- Na grade, recolher estreita a coluna (‹); na lista e no celular, sobe (˄). -->
                  <NuxtIcon
                    v-if="weekDay.orders.length"
                    :name="asGrid ? 'i-lucide-chevron-left' : 'i-lucide-chevron-up'"
                    class="mt-0.5 size-5 shrink-0 text-muted max-md:hidden"
                    aria-hidden="true"
                  />
                  <NuxtIcon v-if="weekDay.orders.length" name="i-lucide-chevron-up" class="mt-0.5 size-5 shrink-0 text-muted md:hidden" aria-hidden="true" />
                </NuxtButton>
                <!-- R7: o dia vazio diz "Nenhuma encomenda" uma vez só, no cabeçalho. -->
                <div
                  v-if="weekDay.orders.length && dayOpen(weekDay, flippedDays)"
                  class="-mx-3 grid divide-y divide-default border-t border-default"
                  data-week-day-orders
                >
                  <PosPreorderRow
                    v-for="card in weekDay.orders"
                    layout="lines"
                    :key="card.ref"
                    :back="back"
                    :card="card"
                    :movable="movable(card)"
                    @dragstart="onDragStart($event, card)"
                    @dragend="endDrag"
                  >
                    <template v-if="canMoveCard(card)" #aside>
                      <PosPreorderMoveMenu
                        :customer-name="card.customer_name"
                        :targets="targetsFor(card)"
                        :busy="move.busy.value || move.loading.value === card.ref"
                        @move="(date) => move.moveTo(card, date)"
                        @other="move.chooseOther(card)"
                      />
                    </template>
                  </PosPreorderRow>
                </div>
                <NuxtButton
                  v-if="weekDay.orders.length"
                  color="primary"
                  variant="ghost"
                  trailing-icon="i-lucide-arrow-right"
                  label="Ver só este dia"
                  class="min-h-11 justify-self-end"
                  :aria-label="`Ver só ${dayColumnTitle(weekDay)}`"
                  data-week-day-only
                  @click="openDay(weekDay.date)"
                />
                </template>
              </NuxtCard>
            </div>
          </div>
        </template>

        <!-- A NOTA DE ESCOPO, como legenda: a ponte da divergência de vocabulário
             ("encomenda" aqui inclui a retirada de hoje). -->
        <p class="flex items-start gap-1.5 px-1 text-xs text-muted max-md:hidden" data-preorders-scope>
          <NuxtIcon name="i-lucide-info" class="mt-px size-3.5 shrink-0" aria-hidden="true" />
          <span>{{ PREORDERS_SCOPE_NOTE }}</span>
        </p>
      </template>
    </template>

    <PosCodeScanner v-model:open="scannerOpen" title="Ler código da encomenda" @code="onScannedOrder" @type="searchBox?.open()" />

    <!-- O REAGENDAR completo, o mesmo do detalhe: "Outra data ou horário…" no menu
         do card, ou depois de o servidor recusar o dia em que o card foi solto. -->
    <PosPreorderRescheduleDialog
      v-if="move.detail.value"
      v-model:open="move.dialogOpen.value"
      :customer-name="move.detail.value.customer_name"
      :current-date="move.detail.value.counter.reschedule.date"
      :current-slot="move.detail.value.counter.reschedule.slot"
      :skus="move.detail.value.counter.reschedule.skus"
      :initial-date="move.dialogDate.value"
      :busy="move.busy.value"
      @confirm="move.confirmDialog"
    />

    <!-- CELULAR: a ação do momento no polegar (o QR da mensagem do cliente). -->
    <template #footer>
      <OperatorActionBar
        :action="{ label: 'Ler código da encomenda', shortLabel: 'Ler código', icon: 'i-lucide-scan-qr-code', onSelect: () => { scannerOpen = true; } }"
        :secondary="compactPhone ? { label: 'Nova encomenda', shortLabel: 'Nova', icon: 'i-lucide-plus', onSelect: () => navigateTo(NEW_ORDER_ROUTE) } : undefined"
        label="Ler código da encomenda"
        data-preorders-scan-bar
      />
    </template>
  </PosPreordersShell>
</template>
