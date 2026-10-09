<script setup lang="ts">
// ENCOMENDAS: a agenda do balcão, numa tela só (redesenho aprovado pelo dono,
// 28/09/2026; a tela da seção do brief de 02/10). Chega-se aqui pela barra lateral.
//
// A arrumação é a do balcão (pedido do dono, 03/10, OBS0310-D): de cima para
// baixo, o cabeçalho, a busca, as pílulas e os cards.
//
//   Cabeçalho           o título e o Período do kit (dia, semana, mês, próximos e
//                       últimos dias, personalizado; ‹ › e a data),
//                       o mesmo lugar em que a Produção, o KDS e o B.I. o põem; à
//                       direita, o que age sobre o que a tela mostra: grade ou
//                       lista (o par de botões de ícone do kit, como o quadro de
//                       comandas do balcão) e o lote das Vias Pedido. Durante a
//                       busca o Período e o lote saem: a busca não tem período.
//   Cliente veio buscar o campo de busca do balcão (`PosSearchField`, o mesmo da
//                       grade de produtos), SEMPRE no topo e já focado: nome,
//                       telefone, CPF/CNPJ, endereço ou número (inclusive o do
//                       iFood). Procura em aberto de QUALQUER data; "Incluir
//                       concluídas" só aparece com a busca digitada (só vale para
//                       ela) e traz as dos últimos 30 dias numa seção à parte.
//                       Um resultado só: Enter abre. Ao lado, Nova encomenda.
//   Pílulas             os recortes de todo dia (A receber, Sem Via Pedido,
//                       Retiradas, Entregas) são a pílula de filtro do kit, em
//                       blocos por pergunta; o "Filtrar" do kit fica para o resto.
//   Hoje                o que falta para o dia, sempre de hoje, qualquer que seja
//                       o período: quantas para entregar, quanto falta receber,
//                       quantas Vias Pedido faltam, e as de pagamento a conferir.
//                       Feita com o que as listas já trazem, sem leitura nova. Na
//                       mesma linha, o resumo do período.
//   Cards               a semana (sete dias lado a lado, ou um embaixo do outro)
//                       ou o dia por janela, em grade ou lista. Na semana o card
//                       se ARRASTA para outro dia: é reagendar (a rota do
//                       Reagendar do detalhe, com a pergunta do kit e o aviso ao
//                       cliente). O menu "Mudar de dia" do card é o mesmo gesto
//                       por teclado e toque.
//
// O estado inteiro mora na URL (`presentation/preorders.parseView`): a volta do
// detalhe cai no mesmo lugar, e o kiosk guarda o favorito.
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
  dayColumnTitle,
  dayToReceiveLine,
  filterDays,
  filterEmptyMessage,
  flattenDays,
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

// ── O lote: do que está visível, só as vias que faltam ──
const tickets = usePosOrderTickets(pos);
const plan = computed(() => (list.value ? printPlan(list.value, days.value) : null));
const printCount = computed(() => plan.value?.refs.length ?? 0);
const maxBatch = computed(() => list.value?.max_batch ?? 0);
const notice = computed(() => batchNotice(printCount.value, maxBatch.value));

async function printMissing() {
  if (plan.value && (await tickets.printBatch(plan.value))) await period.refresh();
}

function openDay(date: string) {
  update({ mode: "day", date });
}

// ── Cliente veio buscar ──
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
const openLimit = computed(() => (result.value ? searchLimitNote(result.value.open.length, result.value.open_count) : ""));
const completedLimit = computed(() => (result.value
  ? searchLimitNote(result.value.completed.length, result.value.completed_count)
  : ""));
const nothingAnywhere = computed(() => !!result.value && result.value.include_completed
  && !result.value.open_count && !result.value.completed_count);

const searchField = useTemplateRef<{ inputRef: HTMLInputElement | null }>("searchField");
onMounted(() => { void nextTick(() => searchField.value?.inputRef?.focus()); });

function openSingle() {
  const only = singleResult(result.value);
  if (only) void navigateTo(preorderDetailPath(only.ref, back.value));
}

// Leitor de código (ou alguém digitando) com o foco fora de qualquer campo: a
// primeira tecla leva o foco ao campo de busca, e o resto da leitura cai nele.
useEventListener(typeof window === "undefined" ? null : window, "keydown", (event: KeyboardEvent) => {
  if (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) return;
  const target = event.target as HTMLElement | null;
  if (target?.closest("input, textarea, select, button, [contenteditable='true'], [role='dialog']")) return;
  searchField.value?.inputRef?.focus();
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
  if (dropDate.value === date) return "border-primary ring-2 ring-primary/40";
  return canDropOn(date, dragging.value, storeToday.value) ? "border-dashed border-primary/50" : "opacity-60";
}

// ── CELULAR (v3 `depois-pdv-celular`): os chips Hoje · Amanhã · Retirada · Entrega
//    no lugar do Período e das pílulas, e "Ler código da encomenda" no polegar. ──
const tomorrow = computed(() => {
  const base = new Date(`${storeToday.value}T12:00:00`);
  base.setDate(base.getDate() + 1);
  return isoDate(base);
});
const phoneChips = computed(() => {
  const isDayView = view.value.mode === "day";
  const cards = allCards.value;
  return [
    { key: "today", label: "Hoje", count: isDayView && view.value.date === storeToday.value ? cards.length : null, active: isDayView && view.value.date === storeToday.value, icon: "" },
    { key: "tomorrow", label: "Amanhã", count: isDayView && view.value.date === tomorrow.value ? cards.length : null, active: isDayView && view.value.date === tomorrow.value, icon: "" },
    { key: "pickup", label: "Retirada", count: cards.filter((c) => c.fulfillment_type !== "delivery").length, active: view.value.fulfillment === "pickup", icon: "lucide:store" },
    { key: "delivery", label: "Entrega", count: cards.filter((c) => c.fulfillment_type === "delivery").length, active: view.value.fulfillment === "delivery", icon: "lucide:bike" },
  ];
});
function pickPhoneChip(key: string) {
  if (key === "today") update({ mode: "day", date: storeToday.value });
  else if (key === "tomorrow") update({ mode: "day", date: tomorrow.value });
  else {
    const fulfillment = key as PreorderFilters["fulfillment"];
    update({ fulfillment: view.value.fulfillment === fulfillment ? "all" : fulfillment });
  }
}
const scannerOpen = ref(false);
// No celular a tela abre no DIA de hoje (v3 celular: "lista de hoje"), salvo quando
// a URL já diz outro recorte (volta do detalhe, favorito).
onMounted(() => {
  if (window.matchMedia("(max-width: 767.98px)").matches && !route.query.mode && !route.query.date && !route.query.q) {
    update({ mode: "day", date: storeToday.value });
  }
});
// O QR da mensagem que o cliente recebeu traz o número da encomenda: a leitura
// vira a busca, e um resultado só abre o detalhe.
function onScannedOrder(code: string) {
  scannedPending.value = true;
  const ref = code.trim().split(/[/?#=]/).filter(Boolean).pop() || code.trim();
  typed.value = ref;
  update({ q: ref });
}
watch(result, (value) => {
  if (value && typed.value && singleResult(value)) {
    // Leitura pelo QR: só abre sozinha quando a busca veio do leitor.
    if (scannedPending.value) {
      scannedPending.value = false;
      openSingle();
    }
  }
});
const scannedPending = ref(false);

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
    @refresh="refreshAll"
  >
    <!-- O PERÍODO na barra da seção. Durante a busca ele sai: a busca não tem período. -->
    <template v-if="!searching" #period>
      <OperatorPeriodPicker
        v-model="periodSelection"
        class="min-w-0 max-md:hidden"
        :presets="PREORDERS_PERIOD_PRESETS"
        custom
        :max-span-days="PREORDERS_MAX_SPAN_DAYS"
        :today="today"
        label="Período das encomendas"
        align="end"
      />
    </template>

    <!-- À DIREITA DA BARRA: grade ou lista, e o lote das Vias Pedido do que se vê. -->
    <template #actions>
      <div class="flex items-center gap-1 max-md:hidden" role="group" aria-label="Arrumação das encomendas" data-preorders-layout>
        <UiIconButton
          v-for="option in LAYOUT_OPTIONS"
          :key="option.value"
          :icon="option.icon"
          :label="option.label"
          :active="layout === option.value"
          :aria-pressed="layout === option.value"
          :data-preorders-layout-option="option.value"
          @click="setLayout(option.value)"
        />
      </div>
      <template v-if="!searching && list && list.count">
        <UiButton
          class="max-md:hidden"
          :disabled="!canPrintBatch(printCount, maxBatch) || tickets.printing.value"
          :loading="tickets.printing.value"
          :title="!tickets.hasPrinter.value ? `${tickets.printerUnavailableReason.value} A Via Pedido sai no balcão que tem impressora.` : (notice ? notice.message : undefined)"
          data-preorders-print
          @click="printMissing"
        >
          <Icon name="lucide:printer" class="size-4" />
          {{ printCtaLabel(printCount, shownCount) }}
        </UiButton>
      </template>
    </template>

    <!-- A LINHA DA BUSCA: quem veio buscar (a urgência, já focada) e, ao lado, a
         porta para anotar uma encomenda nova. -->
    <div class="flex items-center gap-2 md:flex-wrap">
      <section
        class="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-2 md:flex-[1_1_28rem]"
        aria-labelledby="preorders-search-title"
        data-preorders-search-block
      >
        <h1 id="preorders-search-title" class="sr-only">
          <Icon name="lucide:package-search" class="size-5 text-primary" aria-hidden="true" />
          Cliente veio buscar?
        </h1>
        <PosSearchField
          ref="searchField"
          v-model="typed"
          inputmode="search"
          autocomplete="off"
          :placeholder="SEARCH_PLACEHOLDER"
          :aria-label="SEARCH_LABEL"
          data-preorders-search
          @keydown.enter.prevent="openSingle"
        />
        <!-- "Incluir concluídas" só vale para a busca: sem busca digitada, não aparece. -->
        <label v-if="searching" class="inline-flex min-h-8 shrink-0 items-center gap-2 rounded-md px-2 text-sm hover:bg-accent">
          <UiSwitch v-model="includeCompleted" data-preorders-include-completed />
          Incluir concluídas
        </label>
      </section>

      <!-- NOVA ENCOMENDA: a venda, já no modo Encomendas (o seletor Balcão |
           Encomendas da barra da venda), numa comanda livre. -->
      <UiButton
        variant="outline"
        size="lg"
        class="h-8 shrink-0 gap-2"
        aria-label="Nova encomenda"
        data-preorders-new
        @click="navigateTo(NEW_ORDER_ROUTE)"
      >
        <Icon name="lucide:plus" class="size-5" aria-hidden="true" />
        <span class="max-md:sr-only">Nova encomenda</span>
      </UiButton>
    </div>

    <!-- CELULAR: os recortes do dia em chips que rolam, numa linha só. -->
    <div v-if="!searching" class="-mx-4 flex gap-2 overflow-x-auto px-4 no-scrollbar md:hidden" role="group" aria-label="Recortes das encomendas" data-preorders-phone-chips>
      <button
        v-for="chip in phoneChips"
        :key="chip.key"
        type="button"
        class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3.5 op-label transition"
        :class="chip.active ? 'border-primary bg-primary/10 font-semibold' : 'border-border bg-card'"
        :aria-pressed="chip.active"
        :data-preorders-phone-chip="chip.key"
        @click="pickPhoneChip(chip.key)"
      >
        <Icon v-if="chip.active" name="lucide:check" class="size-4 text-primary" aria-hidden="true" />
        <Icon v-else-if="chip.icon" :name="chip.icon" class="size-4 text-muted-foreground" aria-hidden="true" />
        {{ chip.label }}
        <span v-if="chip.count !== null" class="tnum">{{ chip.count }}</span>
      </button>
    </div>

    <!-- ── O RESULTADO DA BUSCA toma o lugar do período. ── -->
    <template v-if="searching">
      <p v-if="!enabled" class="text-sm text-muted-foreground" data-preorders-hint>
        Digite pelo menos {{ SEARCH_MIN_CHARS }} letras ou números para procurar.
      </p>

      <section
        v-else-if="search.pending.value && !result"
        class="grid max-w-3xl gap-2 rounded-md border bg-card p-4"
        aria-live="polite"
        aria-busy="true"
        data-preorders-search-loading
      >
        <UiSkeleton class="h-4 w-32 rounded" label="Procurando encomendas" />
        <UiSkeleton class="h-16 rounded-md" label="Procurando encomendas" />
        <span class="sr-only">Procurando encomendas…</span>
      </section>

      <p
        v-else-if="search.error.value"
        class="flex max-w-3xl flex-wrap items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
        role="alert"
      >
        <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
        <span class="min-w-0 flex-1">{{ httpErrorMessage(search.error.value, "A busca não respondeu.") }} Tente de novo pelo botão ao lado.</span>
        <UiButton variant="outline" size="sm" data-preorders-search-retry @click="search.refresh()">Tentar de novo</UiButton>
      </p>

      <template v-else-if="result">
        <section
          v-if="nothingAnywhere"
          class="grid max-w-3xl justify-items-center gap-2 rounded-md border border-dashed border-border p-8 text-center"
          data-preorders-empty
        >
          <Icon name="lucide:search-x" class="size-6 text-muted-foreground" />
          <p class="text-sm text-muted-foreground">{{ searchEmptyMessage(query, result.completed_days) }}</p>
        </section>

        <template v-else>
          <!-- EM ABERTO: de qualquer data. -->
          <section
            v-if="result.open_count"
            class="grid gap-2"
            :class="asGrid ? '' : 'max-w-3xl'"
            data-preorders-results="open"
          >
            <h2 class="text-sm font-semibold text-muted-foreground">{{ searchOpenHeading(result.open_count) }}</h2>
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
            <p v-if="openLimit" class="text-sm text-muted-foreground">{{ openLimit }}</p>
          </section>

          <section
            v-else
            class="flex max-w-3xl flex-wrap items-center gap-3 rounded-md border border-dashed border-border p-4 text-sm"
            data-preorders-open-empty
          >
            <Icon name="lucide:search-x" class="size-5 shrink-0 text-muted-foreground" />
            <span class="min-w-0 flex-1 text-muted-foreground">{{ searchOpenEmptyMessage(query) }}</span>
            <UiButton
              v-if="!result.include_completed"
              variant="outline"
              size="sm"
              data-preorders-offer-completed
              @click="includeCompleted = true"
            >
              Procurar nas concluídas
            </UiButton>
          </section>

          <!-- CONCLUÍDAS: seção à parte, nunca misturada com as em aberto. -->
          <section
            v-if="result.include_completed"
            class="grid gap-2 border-t border-border pt-4"
            :class="asGrid ? '' : 'max-w-3xl'"
            data-preorders-results="completed"
          >
            <h2 class="text-sm font-semibold text-muted-foreground">
              {{ searchCompletedHeading(result.completed_count, result.completed_days) }}
            </h2>
            <ul :class="cardsClass">
              <li v-for="card in result.completed" :key="card.ref">
                <PosPreorderRow :back="back" :card="card" show-date />
              </li>
            </ul>
            <p v-if="completedLimit" class="text-sm text-muted-foreground">{{ completedLimit }}</p>
          </section>
        </template>
      </template>
    </template>

    <!-- ── O PERÍODO: o dia, ou a semana de segunda a domingo. ── -->
    <template v-else>
      <!-- AS PÍLULAS: os recortes de todo dia, em blocos, e o "Filtrar" para o resto. -->
      <div class="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 max-md:hidden" data-preorders-toolbar>
      <PosPreorderFilters
        v-if="list && list.count"
        v-model="filters"
        :cards="allCards"
        role="group"
        aria-label="Recortar encomendas"
      />

      <!-- HOJE (sempre de hoje) e, na mesma linha, o resumo do PERÍODO na tela: o
           que falta receber primeiro, o total vendido depois e menor (grandezas
           diferentes, nunca somadas). -->
      <div
        v-if="todayLine.length || (list && list.count && showSummary)"
        class="flex flex-wrap items-baseline justify-end gap-x-6 gap-y-1 px-1"
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
              : fact.key === 'check' ? 'tabular-nums text-warning' : 'tabular-nums text-muted-foreground'"
            :data-preorders-today-fact="fact.key"
          >{{ fact.text }}</span>
        </p>
        <div
          v-if="list && list.count && showSummary"
          class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5"
          data-preorders-summary
        >
          <span class="text-sm font-semibold text-muted-foreground">{{ periodSummaryLabel(view.mode) }}</span>
          <p v-if="toReceive" :class="TO_RECEIVE_CLASS" data-preorders-to-receive>{{ toReceive }}</p>
          <p class="text-xs tabular-nums text-muted-foreground" data-preorders-total>{{ summary }}</p>
        </div>
      </div>
      </div>

      <section
        v-if="period.pending.value && !list"
        class="grid gap-3 rounded-md border bg-card p-4"
        aria-live="polite"
        aria-busy="true"
        data-preorders-period-loading
      >
        <div class="flex gap-2">
          <UiSkeleton
            v-for="index in 3"
            :key="index"
            class="h-8 w-24 rounded-full"
            label="Carregando filtros de encomendas"
          />
        </div>
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <UiSkeleton
            v-for="index in 3"
            :key="index"
            class="h-40 rounded-md"
            label="Carregando encomendas"
          />
        </div>
        <span class="sr-only">Carregando as encomendas…</span>
      </section>

      <p
        v-else-if="period.error.value && !list"
        class="flex flex-wrap items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
        role="alert"
      >
        <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
        <span class="min-w-0 flex-1">{{ httpErrorMessage(period.error.value, "Não deu para ler as encomendas agora.") }} Tente de novo pelo botão ao lado.</span>
        <UiButton variant="outline" size="sm" data-preorders-period-retry @click="period.refresh()">Tentar de novo</UiButton>
      </p>

      <template v-else-if="list">
        <section
          v-if="!list.count"
          class="grid justify-items-center gap-2 rounded-md border border-dashed border-border p-8 text-center"
          data-preorders-empty
        >
          <Icon name="lucide:calendar-x" class="size-6 text-muted-foreground" />
          <p class="text-sm text-muted-foreground">{{ periodEmptyMessage(view.mode) }}</p>
        </section>

        <template v-else>
          <section
            v-if="!shownCount"
            class="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground"
            data-preorders-filter-empty
          >
            {{ filterEmptyMessage(view.mode) }}
          </section>

          <!-- DIA: por janela; em grade, os cards em colunas; em lista, a linha inteira. -->
          <div v-else-if="view.mode === 'day' && day" class="grid gap-4" :class="asGrid ? '' : 'max-w-4xl'" data-preorders-day>
            <section v-for="group in groupByWindow(day.orders)" :key="group.key" class="grid gap-2 rounded-md border bg-card p-3" data-preorders-window>
              <h3 class="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                <Icon name="lucide:clock-3" class="size-4" aria-hidden="true" />
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
            </section>
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
              <section
                v-for="weekDay in days"
                :key="weekDay.date"
                class="flex min-w-0 flex-col gap-2 rounded-md border bg-card p-3 shadow-sm transition"
                :class="[
                  weekDay.is_today ? 'border-primary/60 ring-1 ring-primary/10' : 'border-border',
                  dropClass(weekDay.date),
                ]"
                :data-week-day="weekDay.date"
                :data-drop-target="dropDate === weekDay.date ? 'over' : undefined"
                @dragover="onDragOver($event, weekDay.date)"
                @dragleave="onDragLeave($event, weekDay.date)"
                @drop.prevent="onDrop(weekDay.date)"
              >
                <!-- Hoje: o cabeçalho ganha fundo da cor primária e diz "Hoje, ter 29/09";
                     o dia da semana nunca some. Na lista, o cabeçalho é uma linha só. -->
                <button
                  type="button"
                  class="grid min-h-8 gap-1 rounded-md text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  :class="[
                    weekDay.is_today ? '-mx-1 -mt-1 border-primary/30 bg-primary/10 px-2 pt-2 hover:bg-primary/15' : 'border-border hover:bg-accent',
                    weekDay.orders.length ? 'border-b pb-3' : 'pb-1',
                    asGrid ? '' : 'sm:flex sm:flex-wrap sm:items-baseline sm:gap-x-4',
                  ]"
                  :aria-label="`Abrir o dia ${dayColumnTitle(weekDay)}`"
                  :aria-current="weekDay.is_today ? 'date' : undefined"
                  data-week-day-open
                  @click="openDay(weekDay.date)"
                >
                  <span class="text-sm font-semibold" :class="weekDay.is_today ? 'text-primary' : ''" data-week-day-title>
                    {{ dayColumnTitle(weekDay) }}
                  </span>
                  <span class="text-xs tabular-nums text-muted-foreground" data-week-day-total>
                    <template v-if="weekDay.orders_count">{{ preorderCountLabel(weekDay.orders_count) }} · {{ weekDay.total_display }}</template>
                    <template v-else>Nenhuma encomenda</template>
                  </span>
                  <span v-if="dayToReceiveLine(weekDay)" :class="TO_RECEIVE_CLASS" data-week-day-to-receive>
                    {{ dayToReceiveLine(weekDay) }}
                  </span>
                </button>
                <!-- R7: o dia vazio diz "Nenhuma encomenda" uma vez só, no cabeçalho. -->
                <div v-if="weekDay.orders.length" class="grid gap-2">
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
              </section>
            </div>
          </div>
        </template>

        <!-- A NOTA DE ESCOPO, como legenda: a ponte da divergência de vocabulário
             ("encomenda" aqui inclui a retirada de hoje). -->
        <p class="flex items-start gap-1.5 px-1 text-xs text-muted-foreground max-md:hidden" data-preorders-scope>
          <Icon name="lucide:info" class="mt-px size-3.5 shrink-0" aria-hidden="true" />
          <span>{{ PREORDERS_SCOPE_NOTE }}</span>
        </p>
      </template>
    </template>

    <!-- CELULAR: a ação principal no polegar (v3 celular 4), presa acima da barra. -->
    <div class="sticky bottom-20 z-20 -mx-4 -mb-4 bg-gradient-to-t from-background via-background to-transparent px-4 pt-6 pb-3 md:hidden" data-preorders-scan-bar>
      <button
        type="button"
        class="flex h-14 w-full items-center justify-center gap-2.5 rounded-lg bg-primary text-lg font-semibold text-primary-foreground shadow-[0_2px_0_color-mix(in_oklab,var(--primary)_60%,black)]"
        data-preorders-scan
        @click="scannerOpen = true"
      >
        <Icon name="lucide:scan-qr-code" class="size-6" aria-hidden="true" />
        Ler código da encomenda
      </button>
    </div>
    <PosCodeScanner v-model:open="scannerOpen" title="Ler código da encomenda" @code="onScannedOrder" @type="searchField?.inputRef?.focus()" />

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
  </PosPreordersShell>
</template>
