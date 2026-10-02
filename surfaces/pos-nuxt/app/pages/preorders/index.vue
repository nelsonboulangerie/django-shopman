<script setup lang="ts">
// ENCOMENDAS: a agenda do balcão, numa tela só (redesenho aprovado pelo dono,
// 28/09/2026; a tela da seção do brief de 02/10). Chega-se aqui pela barra lateral.
//
//   Barra               o título e o Período do kit (Dia ou Semana, ‹ › e a data),
//                       o mesmo lugar em que a Produção, o KDS e o B.I. o põem.
//                       Durante a busca o Período sai: a busca não tem período.
//   Cliente veio buscar o campo fica SEMPRE no topo e nasce focado: nome,
//                       telefone, CPF/CNPJ, endereço ou número (inclusive o do
//                       iFood). Procura em aberto de QUALQUER data; "Incluir
//                       concluídas" só aparece com a busca digitada (só vale para
//                       ela) e traz as dos últimos 30 dias numa seção à parte.
//                       Um resultado só: Enter abre.
//   Hoje                o que falta para o dia, sempre de hoje, qualquer que seja
//                       o período: quantas para entregar, quanto falta receber,
//                       quantas Vias Pedido faltam, e as de pagamento a conferir.
//                       Feita com o que as listas já trazem, sem leitura nova.
//   Recortes            os de todo dia são botões de um toque (A receber, Sem
//                       Via Pedido, Retiradas, Entregas); o "Filtrar" do kit fica
//                       para o resto. Na mesma linha, o lote: do que está
//                       VISÍVEL, só as vias que ainda não saíram (P2 do dono,
//                       02/10). Reimprimir é no detalhe, uma por vez.
//   Período             a grade da semana (uma árvore só) ou o dia por janela, e
//                       a nota de escopo como legenda abaixo dela.
//   Nova encomenda      ao lado da busca: leva à venda já no modo Encomendas, na
//                       próxima comanda livre, com o assistente na primeira etapa
//                       que falta (P6 do dono, 02/10). A venda que estiver em
//                       andamento fica na comanda dela, no quadro.
//
// O estado inteiro mora na URL (`presentation/preorders.parseView`): a volta do
// detalhe cai no mesmo lugar, e o kiosk guarda o favorito.
import { useEventListener, watchDebounced } from "@vueuse/core";

import { batchNotice, canPrintBatch, isoDate, printCtaLabel } from "~/presentation/orderTickets";
import { preorderDetailPath } from "~/presentation/preorderDetail";
import { NEW_ORDER_ROUTE } from "~/presentation/orderSetup";
import {
  PREORDERS_SCOPE_NOTE,
  SEARCH_LABEL,
  SEARCH_MIN_CHARS,
  SEARCH_PLACEHOLDER,
  TO_RECEIVE_CLASS,
  canSearch,
  dayColumnTitle,
  dayToReceiveLine,
  filterDays,
  filterEmptyMessage,
  flattenDays,
  groupByWindow,
  listSummary,
  parseView,
  periodEmptyMessage,
  periodIsToday,
  periodParams,
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
  viewPath,
  viewQuery,
  type PreorderFilters,
  type PreordersMode,
  type PreordersView,
} from "~/presentation/preorders";
import {
  periodAnchor,
  periodOfDay,
  type PeriodSelection,
} from "../../../../operator-kit/app/presentation/dates";
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
// O "Período" do kit (Tipo 2) em Dia e Semana: ‹ › andam um dia ou uma semana,
// e o estado continua na URL (modo + data).
const periodSelection = computed<PeriodSelection>({
  get: () => periodOfDay(view.value.mode, view.value.date, today),
  set: (next) => update({ mode: next.preset as PreordersMode, date: periodAnchor(next, today) }),
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
        class="ml-auto min-w-0"
        :presets="['day', 'week']"
        :today="today"
        label="Período das encomendas"
        align="end"
      />
    </template>

    <!-- A LINHA DO BALCÃO: quem veio buscar (a urgência, já focada) e, ao lado, a
         porta para anotar uma encomenda nova. -->
    <div class="flex flex-wrap items-center gap-2">
      <!-- CLIENTE VEIO BUSCAR: a urgência do balcão é a primeira região, já focada. -->
      <!-- Uma linha no desktop: o título diz a tarefa, o campo diz o que se digita. -->
      <section
        class="flex min-w-0 flex-[1_1_28rem] flex-wrap items-center gap-x-3 gap-y-2 rounded-md border border-primary/20 bg-primary/5 p-2.5 shadow-sm"
        aria-labelledby="preorders-search-title"
        data-preorders-search-block
      >
        <h1 id="preorders-search-title" class="flex shrink-0 items-center gap-2 font-semibold leading-tight">
          <Icon name="lucide:package-search" class="size-5 text-primary" aria-hidden="true" />
          Cliente veio buscar?
        </h1>
        <UiInput
          ref="searchField"
          v-model="typed"
          type="search"
          inputmode="search"
          autocomplete="off"
          class="h-11 min-w-[min(100%,18rem)] flex-1 bg-background text-base shadow-sm"
          :placeholder="SEARCH_PLACEHOLDER"
          :aria-label="SEARCH_LABEL"
          data-preorders-search
          @keydown.enter.prevent="openSingle"
        />
        <!-- "Incluir concluídas" só vale para a busca: sem busca digitada, não aparece. -->
        <label v-if="searching" class="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-md px-2 text-sm hover:bg-accent">
          <UiSwitch v-model="includeCompleted" data-preorders-include-completed />
          Incluir concluídas
        </label>
      </section>

      <!-- NOVA ENCOMENDA: a venda, já no modo Encomendas (o seletor Balcão |
           Encomendas da barra da venda), numa comanda livre. -->
      <UiButton
        variant="outline"
        size="lg"
        class="h-11 shrink-0 gap-2"
        data-preorders-new
        @click="navigateTo(NEW_ORDER_ROUTE)"
      >
        <Icon name="lucide:plus" class="size-5" aria-hidden="true" />
        Nova encomenda
      </UiButton>
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
        <span class="h-4 w-32 animate-pulse rounded bg-muted" />
        <span class="h-16 animate-pulse rounded-md bg-muted/70" />
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
      <!-- HOJE e os RECORTES com o LOTE: um quadro só. A linha "Hoje" é sempre de
           hoje; os recortes e o lote falam do período na tela. -->
      <section
        v-if="todayLine.length || (list && list.count)"
        class="grid gap-2 rounded-md border bg-card p-2.5 shadow-sm"
        aria-label="Hoje e os recortes das encomendas"
      >
        <p v-if="todayLine.length" class="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-1 text-sm" data-preorders-today>
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

        <!-- RECORTES à esquerda, o LOTE à direita, na mesma linha: imprime, do que se vê, as vias que faltam. -->
        <PosPreorderFilters
          v-if="list && list.count"
          v-model="filters"
          :cards="allCards"
          :class="todayLine.length ? 'border-t pt-2' : ''"
          role="group"
          aria-label="Recortar e imprimir encomendas"
        >
          <template #actions>
            <div class="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1">
              <p v-if="!tickets.hasPrinter.value" class="max-w-64 text-right text-xs text-muted-foreground" data-preorders-no-printer>
                {{ tickets.printerUnavailableReason.value }} A Via Pedido sai no balcão que tem impressora.
              </p>
              <UiButton
                :disabled="!canPrintBatch(printCount, maxBatch) || tickets.printing.value"
                :loading="tickets.printing.value"
                data-preorders-print
                @click="printMissing"
              >
                <Icon name="lucide:printer" class="size-4" />
                {{ printCtaLabel(printCount, shownCount) }}
              </UiButton>
            </div>
          </template>
        </PosPreorderFilters>
      </section>

      <section
        v-if="period.pending.value && !list"
        class="grid gap-3 rounded-md border bg-card p-4"
        aria-live="polite"
        aria-busy="true"
        data-preorders-period-loading
      >
        <div class="flex gap-2">
          <span v-for="index in 3" :key="index" class="h-8 w-24 animate-pulse rounded-full bg-muted" />
        </div>
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <span v-for="index in 3" :key="index" class="h-40 animate-pulse rounded-md bg-muted/70" />
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
          <!-- O resumo do PERÍODO: o que falta receber primeiro, o total vendido depois
               e menor (grandezas diferentes, nunca somadas). -->
          <div
            v-if="showSummary"
            class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-1"
            data-preorders-summary
          >
            <span class="text-sm font-semibold text-muted-foreground">{{ periodSummaryLabel(view.mode) }}</span>
            <p v-if="toReceive" :class="TO_RECEIVE_CLASS" data-preorders-to-receive>{{ toReceive }}</p>
            <p class="text-xs tabular-nums text-muted-foreground" data-preorders-total>{{ summary }}</p>
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
            class="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground"
            data-preorders-filter-empty
          >
            {{ filterEmptyMessage(view.mode) }}
          </section>

          <!-- DIA: por janela, a linha inteira de cada encomenda. -->
          <div v-else-if="view.mode === 'day' && day" class="grid max-w-4xl gap-4" data-preorders-day>
            <section v-for="group in groupByWindow(day.orders)" :key="group.key" class="grid gap-2 rounded-md border bg-card p-3" data-preorders-window>
              <h3 class="flex items-center gap-2 text-sm font-semibold text-muted-foreground">
                <Icon name="lucide:clock-3" class="size-4" aria-hidden="true" />
                {{ group.label }}
              </h3>
              <ul class="grid gap-2">
                <li v-for="card in group.orders" :key="card.ref">
                  <PosPreorderRow :back="back" :card="card" />
                </li>
              </ul>
            </section>
          </div>

          <!-- SEMANA: uma única árvore responsiva. Cada dia conserva largura
               útil; a leitura não troca de DOM nem comprime sete cards frágeis. -->
          <div v-else data-week-board>
            <div class="grid grid-cols-[repeat(auto-fit,minmax(min(17rem,100%),1fr))] items-start gap-3" data-week-grid>
              <section
                v-for="weekDay in days"
                :key="weekDay.date"
                class="flex min-w-0 flex-col gap-2 rounded-md border bg-card p-3 shadow-sm"
                :class="weekDay.is_today ? 'border-primary/60 ring-1 ring-primary/10' : 'border-border'"
                :data-week-day="weekDay.date"
              >
                <!-- Hoje: o cabeçalho ganha fundo da cor primária e diz "Hoje, ter 29/09";
                     o dia da semana nunca some. -->
                <button
                  type="button"
                  class="grid min-h-11 gap-1 rounded-md text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  :class="[
                    weekDay.is_today ? '-mx-1 -mt-1 border-primary/30 bg-primary/10 px-2 pt-2 hover:bg-primary/15' : 'border-border hover:bg-accent',
                    weekDay.orders.length ? 'border-b pb-3' : 'pb-1',
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
                  <PosPreorderRow v-for="card in weekDay.orders" :key="card.ref" :back="back" :card="card" />
                </div>
              </section>
            </div>
          </div>
        </template>

        <!-- A NOTA DE ESCOPO, como legenda: a ponte da divergência de vocabulário
             ("encomenda" aqui inclui a retirada de hoje). -->
        <p class="flex items-start gap-1.5 px-1 text-xs text-muted-foreground" data-preorders-scope>
          <Icon name="lucide:info" class="mt-px size-3.5 shrink-0" aria-hidden="true" />
          <span>{{ PREORDERS_SCOPE_NOTE }}</span>
        </p>
      </template>
    </template>
  </PosPreordersShell>
</template>
