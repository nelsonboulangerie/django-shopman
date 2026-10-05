<script setup lang="ts">
// Qualidade = a revisão do gestor sobre o lote já fechado (quality_reviewed /
// quality_corrected). A classificação continua acontecendo no Fechamento
// (ADR-017 §9): o lote sai do forno classificado, e aqui o gestor confere por
// exceção (QualityGatePanel), confirma o conjunto sem exceção num ato só ou
// corrige a partição de um lote (QcCloseScreen em modo de correção). Mesma
// projeção do Fechamento (o quiosque de QC), outra pergunta.
import type { QCOrderCardProjection } from "~/types/production";
import { isStale, isoForOffset } from "~/presentation/production";
import type { QcPartitionGroup } from "~/presentation/qc";
import { qualityGate } from "~/presentation/qualityGate";
import {
  periodAnchor,
  periodOfDay,
  type PeriodSelection,
} from "../../../operator-kit/app/presentation/dates";

const route = useRoute();
const routeDate = typeof route.query.date === "string" ? route.query.date : "";
const {
  kiosk,
  selectedDate,
  pending,
  error,
  submitting,
  refresh,
  reviewQuality,
  reviewQualityBatch,
  correctQuality,
} = useQcKiosk(routeDate);

const stale = computed(() =>
  isStale({ error: !!error.value, hasData: !!kiosk.value }),
);

useHead({ title: "Qualidade" });

const query = ref(typeof route.query.q === "string" ? route.query.q : "");
watch(
  () => route.query.q,
  (q) => {
    if (typeof q === "string") query.value = q;
  },
);
watch(
  () => route.query.date,
  (value) => {
    if (typeof value === "string") selectedDate.value = value;
  },
);

// Mesmo "Período" do Fechamento: o lote de ontem se revisa a um toque de ‹.
const todayISO = isoForOffset(0);
const period = computed<PeriodSelection>({
  get: () => periodOfDay("day", selectedDate.value, todayISO),
  set: (next) => {
    const day = periodAnchor(next, todayISO);
    selectedDate.value = day === todayISO ? "" : day;
  },
});

// "sáb 03/10 · lotes fechados hoje" sob o título (v4); a hora vem do ponto ao vivo.
const qualitySubtitle = computed(() => {
  const iso = selectedDate.value || todayISO;
  const label = shortDay(iso);
  return selectedDate.value === ""
    ? `${label} · lotes fechados hoje`
    : `${label} · lotes fechados no dia`;
});
function shortDay(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return "";
  const day = new Date(Date.UTC(+match[1]!, +match[2]! - 1, +match[3]!));
  const weekday = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"][day.getUTCDay()];
  return `${weekday} ${match[3]}/${match[2]}`;
}
function shiftDay(delta: number) {
  const base = selectedDate.value || todayISO;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(base);
  if (!match) return;
  const day = new Date(Date.UTC(+match[1]!, +match[2]! - 1, +match[3]! + delta));
  const next = day.toISOString().slice(0, 10);
  period.value = periodOfDay("day", next > todayISO ? todayISO : next, todayISO);
}

// O portão vê TODOS os lotes do dia, sem o filtro da busca: o cartão "N lotes
// sem exceção" precisa contar exatamente o conjunto que o ato confirma (o
// servidor assina esse conjunto). Ele mesmo separa os fechados (sem exceção /
// exceções / confirmados) dos abertos.
const qualityOrders = computed(() => kiosk.value?.orders ?? []);
const batchAvailable = computed(
  () =>
    kiosk.value?.actions.some(
      (action) => action.kind === "review_qc_batch" && action.enabled,
    ) === true,
);
const qualityPendingCount = computed(
  () =>
    (kiosk.value?.orders ?? []).filter(
      (order) => order.closed && !order.quality_reviewed,
    ).length,
);

// A troca "Para confirmar | Confirmados" mora na linha do título (prévia v4
// `producao-qualidade4.html`), com as contagens do mesmo portão do painel.
const view = ref<"pending" | "reviewed">("pending");
const gateCounts = computed(() => {
  const gate = qualityGate(qualityOrders.value);
  return {
    pending: gate.clean.length + gate.exceptions.length,
    reviewed: gate.reviewed.length,
  };
});
// O selo da Qualidade no rail: os lotes fechados esperando a revisão. Fora desta
// tela o selo some (o número sem a leitura viva mentiria).
const productionRail = useProductionRail();
watch(
  qualityPendingCount,
  (count) => {
    productionRail.value.qualityPending = count;
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  productionRail.value.qualityPending = 0;
});

function projectedAction(ref: string) {
  return kiosk.value?.actions.find((action) => action.ref === ref);
}

function correctionAvailable(order: QCOrderCardProjection): boolean {
  return projectedAction(`correct_qc:${order.pk}`)?.enabled === true;
}

function reviewAvailable(order: QCOrderCardProjection): boolean {
  return projectedAction(`review_qc:${order.pk}`)?.enabled === true;
}

// A consequência já está escrita no cartão, antes do gesto: o toque É a
// confirmação (sem caixa do navegador por cima).
async function confirmQuality(order: QCOrderCardProjection) {
  if (!reviewAvailable(order)) return;
  const result = await reviewQuality(order.pk, order.rev);
  if (result.ok) useSonner.success(`Qualidade de ${order.recipe_name} confirmada.`);
}

async function confirmQualityBatch() {
  if (!batchAvailable.value) return;
  const count = (kiosk.value?.orders ?? []).filter(
    (order) => order.closed && !order.quality_reviewed && !order.quality_exception,
  ).length;
  const result = await reviewQualityBatch();
  if (result.ok)
    useSonner.success(
      count === 1 ? "1 lote confirmado." : `${count} lotes confirmados.`,
    );
}

// O atalho dos lotes ainda abertos leva ao Fechamento, no mesmo dia.
function goClose() {
  navigateTo({
    path: "/close",
    query: selectedDate.value ? { date: selectedDate.value } : {},
  });
}

// ── Correção da partição de um lote fechado ─────────────────────────────────
const correcting = ref<QCOrderCardProjection | null>(null);

function openCorrection(order: QCOrderCardProjection) {
  if (!correctionAvailable(order)) return;
  correcting.value = order;
}

function backToGate() {
  correcting.value = null;
}

interface QcCorrectionPayload {
  partition: QcPartitionGroup[];
  reason: string;
}

async function onConfirm(payload: QcCorrectionPayload) {
  const order = correcting.value;
  if (!order) return;
  const result = await correctQuality(
    order.pk,
    order.rev,
    payload.partition,
    payload.reason,
  );
  if (result.ok) {
    useSonner.success("Qualidade corrigida.");
    backToGate();
  }
}

const screenSubtitle = computed(() => {
  const order = correcting.value;
  if (!order) return "";
  return [order.output_sku, order.started_at_display].filter(Boolean).join(" · ");
});
const screenPlanned = computed(() => {
  if (!correcting.value) return null;
  const value = Number(correcting.value.planned_qty);
  return Number.isFinite(value) ? Math.round(value) : null;
});
const screenStarted = computed(() => {
  if (!correcting.value?.started_qty) return null;
  const value = Number(correcting.value.started_qty);
  return Number.isFinite(value) ? Math.round(value) : null;
});
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <ProductionHeader
      v-model:query="query"
      title="Qualidade"
      :subtitle="qualitySubtitle"
      :pending="pending"
      :stale="stale"
      search-placeholder="Buscar lote ou produto"
      @refresh="refresh"
    >
      <!-- Dias anteriores e relatórios moram no ⋯ (v4 legenda 8): o título fica
           com a troca de vista, a lupa e o ⋯. -->
      <template #menu="{ close }">
        <div class="mt-1.5 border-t border-border pt-1.5" data-quality-day-menu>
          <button
            type="button"
            role="menuitem"
            class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent"
            data-quality-previous-day
            @click="
              close();
              shiftDay(-1);
            "
          >
            <Icon name="lucide:chevron-left" class="size-4 text-muted-foreground" />
            Dia anterior
          </button>
          <button
            v-if="selectedDate !== ''"
            type="button"
            role="menuitem"
            class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent"
            @click="
              close();
              shiftDay(1);
            "
          >
            <Icon name="lucide:chevron-right" class="size-4 text-muted-foreground" />
            Dia seguinte
          </button>
          <button
            v-if="selectedDate !== ''"
            type="button"
            role="menuitem"
            class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent"
            @click="
              close();
              selectedDate = '';
            "
          >
            <Icon name="lucide:calendar-check" class="size-4 text-muted-foreground" />
            Voltar para hoje
          </button>
          <NuxtLink
            to="/reports"
            role="menuitem"
            class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent"
            @click="close()"
          >
            <Icon name="lucide:chart-column" class="size-4 text-muted-foreground" />
            Relatórios de qualidade
          </NuxtLink>
        </div>
      </template>
      <template #actions>
        <UiTabs
          v-if="!correcting && kiosk && kiosk.orders.length"
          v-model="view"
          data-quality-view
        >
          <UiTabsList class="grid grid-cols-2 rounded-lg border-0 bg-muted" aria-label="Lotes da Qualidade">
            <UiTabsTrigger value="pending" class="gap-1.5 font-semibold data-[state=active]:bg-card">
              Para confirmar
              <span class="tnum">{{ gateCounts.pending }}</span>
            </UiTabsTrigger>
            <UiTabsTrigger value="reviewed" class="gap-1.5 font-semibold data-[state=active]:bg-card">
              Confirmados
              <span class="tnum">{{ gateCounts.reviewed }}</span>
            </UiTabsTrigger>
          </UiTabsList>
        </UiTabs>
      </template>
    </ProductionHeader>

    <QcCloseScreen
      v-if="correcting && kiosk"
      :key="`correct-${correcting.pk}`"
      :title="correcting.recipe_name"
      :subtitle="screenSubtitle"
      :planned="screenPlanned"
      :started="screenStarted"
      :grades="kiosk.grades"
      :defects="kiosk.defects"
      mode="correct"
      :initial-partition="correcting.partition"
      :submitting="submitting"
      @back="backToGate"
      @confirm="onConfirm($event)"
    />

    <div
      v-else
      class="flex w-full flex-col gap-4 px-4 py-4"
    >
      <div
        v-if="stale"
        role="status"
        aria-live="polite"
        class="flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm font-medium text-warning"
      >
        <Icon name="lucide:wifi-off" class="size-4 shrink-0" />
        <span>Sem atualizar. Mostrando o último painel carregado.</span>
      </div>

      <p
        v-if="pending && !kiosk"
        class="py-10 text-center text-muted-foreground"
      >
        Carregando…
      </p>
      <p
        v-else-if="kiosk && !kiosk.orders.length"
        class="py-10 text-center text-muted-foreground"
      >
        Nenhum lote planejado para hoje.
      </p>

      <QualityGatePanel
        v-if="kiosk && kiosk.orders.length"
        v-model:view="view"
        hide-tabs
        :orders="qualityOrders"
        :query="query"
        :grades="kiosk.grades"
        :defects="kiosk.defects"
        :is-today="selectedDate === ''"
        :batch-available="batchAvailable"
        :submitting="submitting"
        :review-available="reviewAvailable"
        :correction-available="correctionAvailable"
        @confirm-batch="confirmQualityBatch"
        @confirm-one="confirmQuality"
        @correct="openCorrection"
        @go-close="goClose"
      />
    </div>
  </main>
</template>
