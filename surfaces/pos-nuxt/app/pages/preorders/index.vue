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
//   Toolbar             o Período do kit (dia, semana, mês, próximos e últimos
//                       dias, personalizado; ‹ › e a data) e o painel de filtros
//                       único da suíte (`OperatorFilterPanel`): os recortes de todo
//                       dia (A receber, Sem Via Pedido, Retiradas, Entregas) são os
//                       filtros rápidos, o resto mora nos filtros completos. Na
//                       mesa, grade ou lista e, no fim, a leitura: "Hoje" (o que
//                       falta para o dia, sempre de hoje) e o resumo do período.
//                       Durante a busca o Período sai (a busca não tem período) e
//                       entra "Incluir concluídas".
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
  QUICK_FILTERS,
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
  dayToReceiveLine,
  filterDays,
  filterDimensions,
  filterEmptyMessage,
  flattenDays,
  fromPanelFilters,
  groupByWindow,
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
import { filterBarActiveFilters } from "../../../../operator-kit/app/presentation/filterBar";
import type { OperatorHeaderAction } from "../../../../operator-kit/app/presentation/pageHeader";
import type { OperatorScreenAlert } from "../../../../operator-kit/app/presentation/screenState";
import type { ActiveFilters } from "../../../../operator-kit/app/types/filters";
import type { PreorderCard, PreorderDay } from "~/types/preorders";

useHead({ title: "Encomendas" });

const { pos, pending: posPending, refresh: refreshPos } = await usePosTerminal();

const route = useRoute();
const router = useRouter();
const today = isoDate(new Date());
const view = computed(() => parseView(route.query, today));

function update(patch: Partial<PreordersView>) {
  void router.replace({ path: "/preorders", query: viewQuery({ ...view.value, ...patch }, today) });
}

// O recorte de agora: cada linha o leva ao detalhe (`?back=`), e a volta cai nele.
const back = computed(() => viewPath(view.value, today));

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
const showSummary = computed(() => !!summary.value && !periodIsToday(view.value, today));

// ── Hoje: do período, quando ele contém hoje; senão, da leitura do selo da barra ──
const ahead = usePosPreordersAhead();
const todayLine = computed(() => todayFacts(todayOf(list.value, ahead.value)));
// O "Período" do kit (Tipo 2): ‹ › andam um período igual ao escolhido, e o
// estado continua na URL (modo + data, e o fim no personalizado).
const periodSelection = computed<PeriodSelection>({
  get: () => periodSelectionOf(view.value, today),
  set: (next) => update(viewOfPeriod(next, today)),
});

// ── Os filtros: o painel único da suíte ──
const dimensions = computed(() => filterDimensions(allCards.value, filters.value));
const activePanel = computed<ActiveFilters>({
  get: () => toActiveFilters(filters.value),
  set: (next) => { filters.value = fromPanelFilters(filters.value, next); },
});
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
// O hoje da LOJA (o servidor diz na lista), e não o relógio deste dispositivo:
// é ele que decide se um dia já passou.
const storeToday = computed(() => list.value?.today || today);
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
    @refresh="refreshAll"
  >
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

    <!-- O RECORTE: o Período (fora da busca) ou "Incluir concluídas" (só na busca). -->
    <template #filters-primary>
      <OperatorPeriodPicker
        v-if="!searching"
        v-model="periodSelection"
        class="min-w-0"
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
        :quick="[...QUICK_FILTERS]"
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
          variant="ghost"
          square
          :active="layout === option.value"
          active-variant="soft"
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
          <span class="text-sm font-semibold text-muted">{{ periodSummaryLabel(view.mode) }}</span>
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

          <!-- SEMANA: uma única árvore responsiva. Em grade, os dias lado a lado,
               cada um com largura útil; em lista, um embaixo do outro. Cada dia é
               também onde se SOLTA o card arrastado (reagendar). -->
          <div v-else data-week-board>
            <div
              :class="asGrid
                ? 'grid grid-cols-[repeat(auto-fit,minmax(min(17rem,100%),1fr))] items-start gap-3'
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
                :class="[weekDay.is_today ? 'ring-primary/60' : '', dropClass(weekDay.date)]"
                :ui="{ body: 'flex min-w-0 flex-col gap-2 p-3 sm:p-3' }"
                :data-week-day="weekDay.date"
                :data-drop-target="dropDate === weekDay.date ? 'over' : undefined"
                @dragover="onDragOver($event, weekDay.date)"
                @dragleave="onDragLeave($event, weekDay.date)"
                @drop.prevent="onDrop(weekDay.date)"
              >
                <!-- Hoje: o cabeçalho ganha fundo da cor primária e diz "Hoje, ter 29/09";
                     o dia da semana nunca some. Na lista, o cabeçalho é uma linha só. -->
                <NuxtButton
                  color="neutral"
                  variant="ghost"
                  block
                  class="grid justify-start gap-1 text-left"
                  :class="[
                    weekDay.is_today ? 'bg-primary/10 hover:bg-primary/15' : '',
                    asGrid ? '' : 'sm:flex sm:flex-wrap sm:items-baseline sm:gap-x-4',
                  ]"
                  :aria-label="`Abrir o dia ${dayColumnTitle(weekDay)}`"
                  :aria-current="weekDay.is_today ? 'date' : undefined"
                  data-week-day-open
                  @click="openDay(weekDay.date)"
                >
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
                </NuxtButton>
                <!-- R7: o dia vazio diz "Nenhuma encomenda" uma vez só, no cabeçalho. -->
                <div v-if="weekDay.orders.length" class="grid gap-2 border-t border-default pt-2">
                  <PosPreorderRow
                    v-for="card in weekDay.orders"
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
        :action="{ label: 'Ler código da encomenda', icon: 'i-lucide-scan-qr-code', onSelect: () => { scannerOpen = true; } }"
        label="Ler código da encomenda"
        data-preorders-scan-bar
      />
    </template>
  </PosPreordersShell>
</template>
