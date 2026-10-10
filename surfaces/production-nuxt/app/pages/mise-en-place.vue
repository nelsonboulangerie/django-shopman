<script setup lang="ts">
// Preparação (mise en place) — the day's separation & weighing station.
// Two lenses over the same planned WOs:
//   · "Por preparo": each prep with its scaled ingredients — é a pesagem real,
//     e de onde saem as ETIQUETAS CEGAS (código do dia, ingrediente, peso,
//     data; nunca o nome da receita — o mapa código↔preparo é visão de gestor
//     no Admin). Impressão via print CSS: só as etiquetas saem no papel.
//   · "Por insumo": aggregated ingredient list (checklist local ao turno) — bom
//     para conferir provisionamento ("quanto de farinha no total?").
// Tablet/touch-first.
import type { MiseEnPlaceLineProjection } from "~/types/production";
import type { ProductionPrintingSourceProjection } from "~/types/productionPrinting";
import { isStale, isoForOffset } from "~/presentation/production";
import {
  periodAnchor,
  periodOfDay,
  type PeriodSelection,
} from "../../../operator-kit/app/presentation/dates";
import {
  operationalTargetDisplay,
  projectedQuantityDisplay,
} from "~/presentation/weighing";

// Preparação olha hoje por padrão (a pesagem é do dia); amanhã na véspera.
// O "Período" do kit em Dia (Tipo 2): ‹ › andam um dia (amanhã é um toque).
const todayISO = isoForOffset(0);
const selectedDate = ref(todayISO);
const period = computed<PeriodSelection>({
  get: () => periodOfDay("day", selectedDate.value, todayISO),
  set: (next) => {
    selectedDate.value = periodAnchor(next, todayISO);
  },
});

const { stationRef } = useOperatorLock("backstage.operate_production");

const {
  projection,
  lines,
  expand,
  pending,
  error,
  refresh,
  isChecked,
  toggleChecked,
  checkedCount,
  checklistRevisionChanged,
} = useMiseEnPlace(selectedDate, stationRef);
const weighing = useWeighing(selectedDate);

const mode = ref<"insumos" | "preparos">("preparos");
// As duas visões da mesma preparação, como abas que só trocam a lente (`:content="false"`).
const MODE_ITEMS = [
  { label: "Por preparo", value: "preparos" },
  { label: "Por insumo", value: "insumos" },
];

// Tolerante a dado velho: se a atualização falhar mas já houver lista, mantém a lista
// no ar e acende o chip de degradação (dado velho visível > tela em branco).
const staleIngredients = computed(() =>
  isStale({ error: !!error.value, hasData: lines.value.length > 0 }),
);
const staleWeighing = computed(() =>
  isStale({
    error: !!weighing.error.value,
    hasData: weighing.tickets.value.length > 0,
  }),
);

const route = useRoute();
const query = ref(typeof route.query.q === "string" ? route.query.q : "");
watch(
  () => route.query.q,
  (q) => {
    if (typeof q === "string") query.value = q;
  },
);

const visibleLines = computed<MiseEnPlaceLineProjection[]>(() => {
  const term = query.value.trim().toLowerCase();
  if (!term) return lines.value;
  return lines.value.filter(
    (line) =>
      line.sku.toLowerCase().includes(term) ||
      line.name.toLowerCase().includes(term),
  );
});

const visibleTickets = computed(() => {
  const term = query.value.trim().toLowerCase();
  if (!term) return weighing.tickets.value;
  return weighing.tickets.value.filter(
    (ticket) =>
      ticket.name.toLowerCase().includes(term) ||
      ticket.output_sku.toLowerCase().includes(term) ||
      ticket.blind_code.toLowerCase().includes(term) ||
      ticket.ingredients.some((ing) => ing.name.toLowerCase().includes(term)),
  );
});

// A linha aberta mostra as receitas que usam o insumo (o `#expanded` da tabela).
const expandedLines = ref<Record<string, boolean>>({});
const NUM = { class: { th: "text-right", td: "text-right tabular-nums" } };
const lineColumns = computed(() => [
  { id: "done", header: "Separado", enableHiding: false },
  { id: "name", header: "Insumo", enableHiding: false },
  { id: "quantity", header: "Quantidade", meta: NUM },
  ...(projection.value?.has_stock_readings ? [{ id: "available", header: "Saldo", meta: NUM }] : []),
]);

// Dois artefatos de impressão, papéis distintos:
//   · etiquetas CEGAS de pesagem (uma por preparo × ingrediente) — só o
//     código do dia, para qualquer colaborador pesar sem correlacionar;
//   · identificação INTERNA do preparo (uma por preparo) — nunca se apresenta
//     como rótulo de venda. Data e validade vêm do servidor; sem validade
//     responsável, o servidor recusa a emissão.
const printMode = ref<"pesagem" | "preparo">("pesagem");
const printTicketRef = ref<string | null>(null);
const printDialogOpen = ref(false);

function ticketIdentity(ticket: (typeof weighing.tickets.value)[number]) {
  return ticket.ticket_ref?.trim() || ticket.recipe_ref;
}

const printableTickets = computed(() => {
  if (!printTicketRef.value) return weighing.tickets.value;
  return weighing.tickets.value.filter(
    (ticket) => ticketIdentity(ticket) === printTicketRef.value,
  );
});

const labels = computed(() =>
  printableTickets.value.flatMap((ticket) =>
    ticket.ingredients.map((ing, index) => ({
      code: ticket.blind_code,
      ingredient: ing.name,
      sku: ing.sku,
      weight: operationalTargetDisplay(
        ing.target_display,
        ing.quantity_display,
      ),
      annotation: ing.annotation,
      date: weighing.dateDisplay.value,
      key: `${ticketIdentity(ticket)}-${ing.sku}-${index}`,
    })),
  ),
);

const printProjection = computed(
  () => weighing.projection.value as ProductionPrintingSourceProjection | null,
);
const scaleRoundingNote = computed(
  () => printProjection.value?.scale_rounding_note || "",
);

function openLabelsPreview(
  kind: "pesagem" | "preparo",
  ticketRef: string | null = null,
) {
  printMode.value = kind;
  printTicketRef.value = ticketRef;
  mode.value = "preparos";
  printDialogOpen.value = true;
}

const isPending = computed(() =>
  mode.value === "insumos" ? pending.value : weighing.pending.value,
);
function refreshAll() {
  refresh();
  weighing.refresh();
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <div class="print:hidden">
      <ProductionHeader
        v-model:query="query"
        title="Preparação"
        :count="mode === 'insumos' ? lines.length : visibleTickets.length"
        :count-label="mode === 'insumos' ? 'insumos' : 'preparos'"
        :pending="isPending"
        @refresh="refreshAll()"
      >
        <template #primary>
          <OperatorPeriodPicker
            v-model="period"
            compact
            class="[&_[data-period-today]]:hidden"
            :presets="['day']"
            :today="todayISO"
            label="Data da preparação"
            align="end"
          />
        </template>
      </ProductionHeader>
    </div>

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4 print:hidden">
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <!-- Modo: alterna duas visões da mesma preparação. -->
        <NuxtTabs
          v-model="mode"
          :items="MODE_ITEMS"
          :content="false"
          variant="pill"
          aria-label="Modo de visualização"
        />

        <span
          v-if="mode === 'insumos' && projection?.work_order_count"
          class="text-sm tabular-nums text-muted-foreground"
        >
          {{ checkedCount }}/{{ lines.length }} separados
        </span>

        <span
          v-if="mode === 'insumos' && lines.length"
          class="flex items-center gap-1.5 text-xs text-muted-foreground"
        >
          <Icon name="lucide:info" class="size-4 shrink-0" />
          Checklist local {{ stationRef ? "desta estação" : "deste dispositivo" }} · não é registro de auditoria
        </span>

        <div class="ml-auto flex flex-wrap items-center gap-3">
          <NuxtCheckbox
            v-if="mode === 'insumos'"
            v-model="expand"
            label="Explodir até matéria-prima"
          />
          <template v-if="mode === 'preparos' && visibleTickets.length">
            <NuxtButton
              icon="i-lucide-printer"
              label="Etiquetas de pesagem"
              @click="openLabelsPreview('pesagem')"
            />
            <NuxtButton
              color="neutral"
              variant="outline"
              icon="i-lucide-tag"
              label="Identificação interna"
              title="Identificação interna: nome, data prevista e validade configurada"
              @click="openLabelsPreview('preparo')"
            />
          </template>
        </div>
      </div>

      <!-- ── Modo Insumos: agregado do dia (provisionamento + checklist) ── -->
      <template v-if="mode === 'insumos'">
        <div
          v-if="checklistRevisionChanged"
          role="status"
          aria-live="polite"
          class="mb-3 flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm font-medium text-warning"
        >
          <Icon name="lucide:refresh-cw" class="size-4 shrink-0" />
          <span>O planejamento mudou. Confira esta revisão; as marcações da lista anterior foram limpas.</span>
        </div>
        <p
          v-if="pending && !lines.length"
          class="text-sm text-muted-foreground"
        >
          Carregando…
        </p>
        <div
          v-else-if="error && !lines.length"
          class="grid place-items-center gap-2 rounded-md border border-dashed border-destructive/30 py-16 text-center text-muted-foreground"
        >
          <Icon name="lucide:cloud-off" class="size-8 text-destructive/70" />
          <p class="text-base font-medium text-foreground">
            Não foi possível carregar a lista.
          </p>
          <NuxtButton
            class="mt-1"
            color="neutral"
            variant="outline"
            icon="i-lucide-refresh-cw"
            label="Tentar de novo"
            @click="refresh()"
          />
        </div>

        <div
          v-else-if="!lines.length"
          class="grid place-items-center gap-2 rounded-md border border-dashed py-16 text-center text-muted-foreground"
        >
          <Icon name="lucide:scale" class="size-8" />
          <p class="text-base font-medium">Nada para separar nesta data.</p>
          <NuxtLink
            to="/plan"
            class="inline-flex min-h-8 items-center text-sm text-primary underline-offset-2 hover:underline"
            >Planejar produção</NuxtLink
          >
        </div>

        <template v-else>
          <div
            v-if="staleIngredients"
            role="status"
            aria-live="polite"
            class="mb-3 flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm font-medium text-warning"
          >
            <Icon name="lucide:wifi-off" class="size-4 shrink-0" />
            <span>Sem atualizar: mostrando a última lista carregada.</span>
          </div>
          <!-- A margem já está somada nas quantidades. Ela precisa de motivo à
               vista: no modo explodido a linha do preparo some, e este
               cabeçalho é o único lugar onde a explicação cabe. -->
          <p
            v-if="projection?.yield_margin_applied"
            class="mb-3 flex items-start gap-2 rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground"
          >
            <Icon name="lucide:scale" class="mt-0.5 size-4 shrink-0" />
            <span>{{ projection.yield_margin_note }}</span>
          </p>
          <!-- A tabela da suíte: o insumo fica (fixado); a caixa marca o separado (é
               lista de conferência da bancada, não seleção de linhas); a seta abre as
               receitas que usam o insumo. -->
          <OperatorTable
            v-model:expanded="expandedLines"
            :data="visibleLines"
            :columns="lineColumns"
            :row-key="(line) => line.sku"
            :row-label="(line) => line.name"
            :row-class="(line) => (isChecked(line.sku) ? 'bg-muted/40 text-muted-foreground' : '')"
            pinned="name"
            :empty-title="query ? `Nenhum insumo para “${query.trim()}”.` : 'Nenhum insumo para separar.'"
            caption="Insumos da preparação"
            data-mise-lines
          >
            <template #done-header><span class="sr-only">Separado</span></template>
            <template #done-cell="{ row }">
              <NuxtCheckbox
                :model-value="isChecked(row.original.sku)"
                :aria-label="`Marcar ${row.original.name} como separado`"
                @update:model-value="toggleChecked(row.original.sku)"
              />
            </template>
            <template #name-cell="{ row }">
              <span
                class="block font-semibold"
                :class="isChecked(row.original.sku) ? 'line-through decoration-1' : ''"
                >{{ row.original.name }}</span
              >
              <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
                <!-- Insumo sem nome cadastrado tem o SKU como nome; repetir embaixo
                     seria a mesma linha duas vezes. -->
                <span v-if="row.original.name !== row.original.sku">{{ row.original.sku }}</span>
                <NuxtBadge v-if="row.original.is_subrecipe" color="neutral" label="Pré-preparo" />
              </span>
            </template>
            <template #quantity-cell="{ row }">
              <span class="font-semibold">{{ projectedQuantityDisplay(row.original.quantity_display) }}</span>
              <!-- O mesmo peso dito na contagem da bancada. O "≈" vem do servidor quando
                   o fator é aproximado; aqui só se mostra. -->
              <span v-if="row.original.annotation" class="block text-xs text-muted-foreground">{{
                row.original.annotation
              }}</span>
              <!-- Os gramas a mais são margem, e a linha diz por quê: número que cresceu
                   sozinho não entra nesta lista. O texto do motivo vem pronto do servidor. -->
              <span
                v-if="row.original.margin_display"
                class="block text-xs text-muted-foreground"
                :title="row.original.margin_reason"
                >{{ row.original.margin_display }}</span
              >
            </template>
            <template #available-cell="{ row }">
              <span :class="row.original.is_short ? 'font-semibold text-error' : 'text-muted-foreground'">
                {{
                  row.original.available_display
                    ? projectedQuantityDisplay(row.original.available_display)
                    : "—"
                }}
              </span>
              <span v-if="row.original.is_short" class="block text-xs font-medium text-error">Falta</span>
            </template>
            <template #expanded="{ row }">
              <ul v-if="row.original.breakdown.length" class="flex flex-col gap-1 text-xs text-muted-foreground">
                <li
                  v-for="item in row.original.breakdown"
                  :key="item.output_sku"
                  class="flex items-center justify-between gap-3"
                >
                  <span
                    >{{ item.recipe_name }} <span class="opacity-70">({{ item.output_sku }})</span></span
                  >
                  <span class="tabular-nums">{{ projectedQuantityDisplay(item.quantity_display) }}</span>
                </li>
                <!-- A quebra por receita NÃO fecha com o total quando há margem, e é aqui
                     que a diferença se explica por extenso, em vez de virar conta que
                     não bate. -->
                <li v-if="row.original.margin_reason" class="border-t pt-1 italic">
                  {{ row.original.margin_reason }}
                </li>
              </ul>
              <p v-else class="text-xs text-muted-foreground">
                Este insumo entra direto na ficha, sem receita intermediária.
              </p>
            </template>
          </OperatorTable>
        </template>
      </template>

      <!-- ── Modo Por preparo: a pesagem real (fonte das etiquetas) ── -->
      <template v-else>
        <p
          v-if="weighing.pending.value && !weighing.tickets.value.length"
          class="text-sm text-muted-foreground"
        >
          Carregando…
        </p>
        <div
          v-else-if="weighing.error.value && !weighing.tickets.value.length"
          class="grid place-items-center gap-2 rounded-md border border-dashed border-destructive/30 py-16 text-center text-muted-foreground"
        >
          <Icon name="lucide:cloud-off" class="size-8 text-destructive/70" />
          <p class="text-base font-medium text-foreground">
            Não foi possível carregar os preparos.
          </p>
          <NuxtButton
            class="mt-1"
            color="neutral"
            variant="outline"
            icon="i-lucide-refresh-cw"
            label="Tentar de novo"
            @click="weighing.refresh()"
          />
        </div>

        <div
          v-else-if="!weighing.tickets.value.length"
          class="grid place-items-center gap-2 rounded-md border border-dashed py-16 text-center text-muted-foreground"
        >
          <Icon name="lucide:scale" class="size-8" />
          <p class="text-base font-medium">
            Nenhum preparo para pesar nesta data.
          </p>
          <NuxtLink
            to="/plan"
            class="inline-flex min-h-8 items-center text-sm text-primary underline-offset-2 hover:underline"
            >Planejar produção</NuxtLink
          >
        </div>

        <template v-else>
          <div
            v-if="staleWeighing"
            role="status"
            aria-live="polite"
            class="mb-3 flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm font-medium text-warning"
          >
            <Icon name="lucide:wifi-off" class="size-4 shrink-0" />
            <span
              >Sem atualizar: mostrando os últimos preparos carregados.</span
            >
          </div>
          <p
            v-if="scaleRoundingNote"
            class="mb-3 flex items-center gap-1.5 text-xs text-muted-foreground"
          >
            <Icon name="lucide:scale" class="size-3.5" />
            {{ scaleRoundingNote }}
          </p>
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <article
              v-for="ticket in visibleTickets"
              :key="ticketIdentity(ticket)"
              class="flex flex-col gap-2.5 rounded-xl border border-border bg-card p-4"
            >
              <header class="flex items-start justify-between gap-2">
                <div class="flex min-w-0 items-start gap-2">
                  <span
                    class="shrink-0 rounded-md border border-primary/30 bg-primary/5 px-2 py-0.5 font-mono text-sm font-bold tracking-wide text-primary"
                    title="Código cego do dia: vai nas etiquetas no lugar do nome"
                    >{{ ticket.blind_code }}</span
                  >
                  <div class="min-w-0">
                    <p class="op-title leading-tight">
                      {{ ticket.name }}
                    </p>
                    <p class="text-xs text-muted-foreground">
                      {{ ticket.output_sku
                      }}<template
                        v-if="
                          ticket.total_weight_display ||
                          ticket.dough_weight_display
                        "
                      >
                        · Peso total
                        {{
                          operationalTargetDisplay(
                            ticket.total_weight_display,
                            ticket.dough_weight_display,
                          )
                        }}</template
                      >
                    </p>
                  </div>
                </div>
                <NuxtButton
                  class="shrink-0"
                  color="neutral"
                  variant="outline"
                  icon="i-lucide-printer"
                  square
                  :aria-label="`Abrir etiquetas de pesagem de ${ticket.name}`"
                  :title="`Conferir etiquetas de ${ticket.name}`"
                  @click="openLabelsPreview('pesagem', ticketIdentity(ticket))"
                />
              </header>
              <ul class="flex flex-col divide-y text-sm">
                <li
                  v-for="ing in ticket.ingredients"
                  :key="ing.sku"
                  class="flex items-center justify-between gap-3 py-1.5"
                >
                  <span class="min-w-0">
                    <span class="block truncate font-medium">{{
                      ing.name
                    }}</span>
                    <span
                      class="block truncate font-mono text-xs text-muted-foreground"
                      >{{ ing.sku }}</span
                    >
                  </span>
                  <span class="shrink-0 text-right">
                    <span class="block font-semibold tabular-nums">{{
                      operationalTargetDisplay(
                        ing.target_display,
                        ing.quantity_display,
                      )
                    }}</span>
                    <span
                      v-if="ing.annotation"
                      class="block text-xs text-muted-foreground"
                      >{{ ing.annotation }}</span
                    >
                  </span>
                </li>
              </ul>
              <footer
                v-if="ticket.output_quantity_display || ticket.sources_display"
                class="space-y-0.5 text-xs text-muted-foreground"
              >
                <p v-if="ticket.output_quantity_display">
                  Rendimento:
                  {{ projectedQuantityDisplay(ticket.output_quantity_display) }}
                </p>
                <p v-if="ticket.sources_display">
                  Objetivo: {{ ticket.sources_display }}
                </p>
              </footer>
            </article>
          </div>
          <p
            v-if="
              query && !visibleTickets.length && weighing.tickets.value.length
            "
            class="mt-3 rounded-md border border-dashed p-3 text-center text-sm text-muted-foreground"
          >
            Nenhum preparo para “{{ query.trim() }}”.
          </p>
        </template>
      </template>
    </section>

    <ProductionLabelPrintDialog
      v-model:open="printDialogOpen"
      :print-mode="printMode"
      :labels="labels"
      :tickets="printableTickets"
      :selected-date="selectedDate"
      :date-display="weighing.dateDisplay.value"
      :projection="printProjection"
      :refresh-projection="weighing.refresh"
    />
  </main>
</template>
