<script setup lang="ts">
// ENCOMENDAS — uma tela só, com o panorama da semana no centro (redesenho
// aprovado pelo dono, 28/09/2026). Chega-se aqui pela barra lateral.
//
//   Cliente veio buscar — o campo fica SEMPRE no topo e nasce focado: nome,
//                         telefone, CPF/CNPJ, endereço ou número (inclusive o do
//                         iFood). Procura em aberto de QUALQUER data; "Incluir
//                         concluídas" traz as dos últimos 30 dias numa seção à
//                         parte, nunca misturadas. Um resultado só: Enter abre.
//   Dia | Semana        — as abas da barra. ‹ › anda um dia ou uma semana, e a
//                         data escolhe o dia (a semana é a que o contém, de
//                         segunda a domingo). Tocar no dia da grade abre o Dia.
//   Filtros             — chips combináveis: recebimento, pagamento, Via Pedido.
//   Imprimir N vias     — o lote da Via Pedido do que está VISÍVEL. A tela de
//                         lote ("Via Pedido – painel") morreu aqui.
//
// O estado inteiro mora na URL (`presentation/preorders.parseView`): a volta do
// detalhe cai no mesmo lugar, e o kiosk guarda o favorito.
import { useEventListener, watchDebounced } from "@vueuse/core";

import { batchNotice, canPrintBatch, isoDate, printCtaLabel } from "~/presentation/orderTickets";
import { preorderDetailPath } from "~/presentation/preorderDetail";
import {
  PREORDERS_SCOPE_NOTE,
  SEARCH_MIN_CHARS,
  SEARCH_PLACEHOLDER,
  canSearch,
  dayColumnTitle,
  dayToReceiveLine,
  filterDays,
  filterEmptyMessage,
  flattenDays,
  groupByWindow,
  hasFilters,
  listSummary,
  modeSections,
  NO_FILTERS,
  parseView,
  periodEmptyMessage,
  periodParams,
  periodTitle,
  preorderCountLabel,
  printPlan,
  searchCompletedHeading,
  searchEmptyMessage,
  searchLimitNote,
  searchOpenEmptyMessage,
  searchOpenHeading,
  showsToday,
  singleResult,
  stepDate,
  stepLabels,
  toReceiveLine,
  viewPath,
  viewQuery,
  type PreorderFilters,
  type PreordersView,
} from "~/presentation/preorders";
import type { PreorderDay } from "~/types/preorders";

useHead({ title: "Encomendas" });

const { pos, pending: posPending, refresh: refreshPos } = await usePosTerminal();

const route = useRoute();
const router = useRouter();
const today = isoDate(new Date());
const view = computed(() => parseView(route.query, today));

function update(patch: Partial<PreordersView>) {
  void router.replace({ path: "/preorders", query: viewQuery({ ...view.value, ...patch }, today) });
}

const sections = computed(() => modeSections(view.value, today));
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
const steps = computed(() => stepLabels(view.value.mode));

// ── Imprimir N vias (o que está visível) ──
const tickets = usePosOrderTickets(pos);
const plan = computed(() => (list.value ? printPlan(list.value, days.value) : null));
const printCount = computed(() => plan.value?.refs.length ?? 0);
const maxBatch = computed(() => list.value?.max_batch ?? 0);
const notice = computed(() => batchNotice(printCount.value, maxBatch.value));

async function printVisible() {
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
    :sections="sections"
    :current="searching ? '' : view.mode"
    wide
    @refresh="refreshAll"
  >
    <!-- CLIENTE VEIO BUSCAR: sempre no topo, já com o foco. -->
    <div class="grid max-w-3xl gap-1.5" data-preorders-search-block>
      <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
        <UiInput
          ref="searchField"
          v-model="typed"
          type="search"
          inputmode="search"
          autocomplete="off"
          class="h-12 min-w-0 flex-1 basis-80 text-base"
          :placeholder="SEARCH_PLACEHOLDER"
          :aria-label="SEARCH_PLACEHOLDER"
          data-preorders-search
          @keydown.enter.prevent="openSingle"
        />
        <label class="inline-flex shrink-0 items-center gap-1 text-sm">
          <UiSwitch v-model="includeCompleted" data-preorders-include-completed />
          Incluir concluídas
        </label>
      </div>
    </div>

    <!-- ── O RESULTADO DA BUSCA toma o lugar do período. ── -->
    <template v-if="searching">
      <p v-if="!enabled" class="text-sm text-muted-foreground" data-preorders-hint>
        Digite pelo menos {{ SEARCH_MIN_CHARS }} letras ou números para procurar.
      </p>

      <p v-else-if="search.pending.value && !result" class="p-4 text-sm text-muted-foreground">
        Procurando…
      </p>

      <p
        v-else-if="search.error.value"
        class="flex max-w-3xl items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
      >
        <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
        <span>{{ httpErrorMessage(search.error.value, "A busca não respondeu.") }} Tente de novo.</span>
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
            class="grid max-w-3xl gap-2"
            data-preorders-results="open"
          >
            <h2 class="text-sm font-semibold text-muted-foreground">{{ searchOpenHeading(result.open_count) }}</h2>
            <ul class="grid gap-2">
              <li v-for="card in result.open" :key="card.ref">
                <PosPreorderRow :back="back" :card="card" show-date />
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
            class="grid max-w-3xl gap-2 border-t border-border pt-4"
            data-preorders-results="completed"
          >
            <h2 class="text-sm font-semibold text-muted-foreground">
              {{ searchCompletedHeading(result.completed_count, result.completed_days) }}
            </h2>
            <ul class="grid gap-2">
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
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <UiButton variant="outline" size="icon" :aria-label="steps.prev" data-period-prev @click="update({ date: stepDate(view, -1) })">
            <Icon name="lucide:chevron-left" class="size-5" />
          </UiButton>
          <h1 class="text-lg font-semibold" data-period-title>{{ periodTitle(view, today) }}</h1>
          <UiButton variant="outline" size="icon" :aria-label="steps.next" data-period-next @click="update({ date: stepDate(view, 1) })">
            <Icon name="lucide:chevron-right" class="size-5" />
          </UiButton>
          <UiInput
            type="date"
            class="h-11 w-auto"
            aria-label="Escolher a data"
            :model-value="view.date"
            data-period-date
            @update:model-value="(value: string) => value && update({ date: value })"
          />
          <UiButton v-if="!showsToday(view, today)" variant="ghost" size="sm" data-period-today @click="update({ date: today })">
            Voltar para hoje
          </UiButton>
        </div>
        <p v-if="summary" class="text-sm tabular-nums text-muted-foreground" data-preorders-summary>
          {{ summary }}<template v-if="toReceive"> · <span class="font-semibold text-foreground" data-preorders-to-receive>{{ toReceive }}</span></template>
        </p>
      </div>
      <p class="text-sm text-muted-foreground">{{ PREORDERS_SCOPE_NOTE }}</p>

      <p v-if="period.pending.value && !list" class="p-4 text-sm text-muted-foreground">
        Carregando as encomendas…
      </p>

      <p
        v-else-if="period.error.value && !list"
        class="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
      >
        <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
        <span>{{ httpErrorMessage(period.error.value, "Não deu para ler as encomendas agora.") }} Tente de novo em Atualizar, no menu ao lado.</span>
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
          <!-- FILTROS à esquerda, o LOTE à direita: "Imprimir N vias" imprime o que se vê. -->
          <div class="flex flex-wrap items-start justify-between gap-3">
            <PosPreorderFilters v-model="filters" :cards="allCards" class="min-w-0 flex-1" />
            <div class="grid shrink-0 justify-items-end gap-1">
              <UiButton
                :disabled="!canPrintBatch(printCount, maxBatch) || tickets.printing.value"
                :loading="tickets.printing.value"
                data-preorders-print
                @click="printVisible"
              >
                <Icon name="lucide:printer" class="size-4" />
                {{ printCtaLabel(printCount) }}
              </UiButton>
              <p v-if="!tickets.hasPrinter.value" class="max-w-72 text-right text-xs text-muted-foreground" data-preorders-no-printer>
                {{ tickets.printerUnavailableReason.value }} A Via Pedido sai no balcão que tem impressora.
              </p>
            </div>
          </div>

          <p
            v-if="notice"
            class="flex items-start gap-2 rounded-md border p-3 text-sm"
            :class="notice.tone === 'danger' ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'border-warning/30 bg-warning/10 text-warning'"
            data-preorders-print-notice
          >
            <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
            <span>{{ notice.message }}</span>
          </p>

          <section
            v-if="!shownCount"
            class="flex flex-wrap items-center justify-center gap-3 rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground"
            data-preorders-filter-empty
          >
            <span>{{ filterEmptyMessage(view.mode) }}</span>
            <UiButton v-if="hasFilters(filters)" variant="outline" size="sm" @click="filters = { ...NO_FILTERS }">
              Mostrar todas
            </UiButton>
          </section>

          <!-- DIA: por janela, a linha inteira de cada encomenda. -->
          <div v-else-if="view.mode === 'day' && day" class="grid max-w-3xl gap-4" data-preorders-day>
            <section v-for="group in groupByWindow(day.orders)" :key="group.key" class="grid gap-2" data-preorders-window>
              <h2 class="text-sm font-semibold text-muted-foreground">{{ group.label }}</h2>
              <ul class="grid gap-2">
                <li v-for="card in group.orders" :key="card.ref">
                  <PosPreorderRow :back="back" :card="card" />
                </li>
              </ul>
            </section>
          </div>

          <!-- SEMANA: decide pela largura da ÁREA, não da tela — com a barra
               lateral aberta, 1024px de tela davam colunas estreitas demais. -->
          <div v-else class="@container">
            <!-- GRADE (área larga): sete colunas de segunda a domingo. -->
            <div class="hidden gap-2 @4xl:grid @4xl:grid-cols-7" data-week-grid>
              <section
                v-for="weekDay in days"
                :key="weekDay.date"
                class="flex min-w-0 flex-col gap-2 rounded-md border bg-muted/30 p-2"
                :class="weekDay.is_today ? 'border-primary/50' : 'border-border'"
                :data-week-day="weekDay.date"
              >
                <button
                  type="button"
                  class="grid gap-0.5 rounded-md border-b border-border pb-2 text-left hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  :aria-label="`Abrir o dia ${dayColumnTitle(weekDay)}`"
                  data-week-day-open
                  @click="openDay(weekDay.date)"
                >
                  <span class="text-sm font-semibold capitalize" :class="weekDay.is_today ? 'text-primary' : ''">{{ dayColumnTitle(weekDay) }}</span>
                  <span class="text-xs tabular-nums text-muted-foreground" data-week-day-total>
                    <template v-if="weekDay.orders_count">{{ preorderCountLabel(weekDay.orders_count) }} · {{ weekDay.total_display }}</template>
                    <template v-else>Nenhuma encomenda</template>
                  </span>
                  <span v-if="dayToReceiveLine(weekDay)" class="text-xs font-semibold tabular-nums text-foreground" data-week-day-to-receive>
                    {{ dayToReceiveLine(weekDay) }}
                  </span>
                </button>
                <PosPreorderRow v-for="card in weekDay.orders" :key="card.ref" :back="back" :card="card" compact />
              </section>
            </div>

            <!-- LISTA (área estreita): um bloco por dia, na mesma ordem. -->
            <div class="grid gap-4 @4xl:hidden" data-week-list>
              <section v-for="weekDay in days" :key="weekDay.date" class="grid gap-2">
                <button
                  type="button"
                  class="flex flex-wrap items-baseline justify-between gap-2 rounded-md text-left text-sm font-semibold hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  :aria-label="`Abrir o dia ${dayColumnTitle(weekDay)}`"
                  @click="openDay(weekDay.date)"
                >
                  <span class="capitalize" :class="weekDay.is_today ? 'text-primary' : ''">{{ dayColumnTitle(weekDay) }}</span>
                  <span class="text-xs font-normal tabular-nums text-muted-foreground">
                    <template v-if="weekDay.orders_count">{{ preorderCountLabel(weekDay.orders_count) }} · {{ weekDay.total_display }}</template>
                    <template v-else>Nenhuma encomenda</template>
                    <template v-if="dayToReceiveLine(weekDay)"> · <span class="font-semibold text-foreground">{{ dayToReceiveLine(weekDay) }}</span></template>
                  </span>
                </button>
                <PosPreorderRow v-for="card in weekDay.orders" :key="card.ref" :back="back" :card="card" />
              </section>
            </div>
          </div>
        </template>
      </template>
    </template>
  </PosPreordersShell>
</template>
