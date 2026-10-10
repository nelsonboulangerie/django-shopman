<script setup lang="ts">
// Portão de qualidade (P19/P20, decisão do dono 03/10: qualidade em lote).
// Forma CONFERÊNCIA por exceção: o que bate vira UM cartão e UM ato, com a
// consequência escrita antes do gesto; o que não bate fica à parte, um a um,
// com a partição, o motivo e a referência para decidir. O portão humano
// continua: nada é liberado sozinho. Tablet deitado: duas colunas.
import type {
  QCDefectProjection,
  QCGradeProjection,
  QCOrderCardProjection,
} from "~/types/production";
import {
  alertsReleased,
  batchConfirmLabel,
  cleanSummary,
  closersSummary,
  exceptionBadge,
  exceptionReference,
  exceptionSegments,
  lotQuantityLabel,
  plural,
  qualityGate,
  reviewedSummary,
} from "~/presentation/qualityGate";

const props = defineProps<{
  orders: QCOrderCardProjection[];
  grades: QCGradeProjection[];
  defects: QCDefectProjection[];
  /** Data da tela é hoje? Muda só o título ("de hoje"). */
  isToday: boolean;
  batchAvailable: boolean;
  submitting: boolean;
  reviewAvailable: (order: QCOrderCardProjection) => boolean;
  correctionAvailable: (order: QCOrderCardProjection) => boolean;
  /** A troca de vista mora no cabeçalho da página. */
  hideTabs?: boolean;
  /** Busca da tela (lupa): recorta as exceções e os confirmados. O conjunto sem
   *  exceção NÃO se recorta: o ato confirma exatamente o que o servidor assina. */
  query?: string;
}>();

const emit = defineEmits<{
  "confirm-batch": [];
  "confirm-one": [order: QCOrderCardProjection];
  correct: [order: QCOrderCardProjection];
  "go-close": [];
}>();

type View = "pending" | "reviewed";
// A troca "Para confirmar | Confirmados" pode morar no cabeçalho da tela (V4-PROD, a
// prévia `producao-qualidade4.html` a põe na linha do título): a página segura o
// estado e passa `hide-tabs`. Sem isso, o painel mostra a troca dele.
const view = defineModel<View>("view", { default: "pending" });
// A troca, quando é do painel: as duas vistas com a contagem de cada uma.
const showAllClean = ref(false);

const gate = computed(() => qualityGate(props.orders));
const pendingCount = computed(
  () => gate.value.clean.length + gate.value.exceptions.length,
);
const viewTabs = computed(() => [
  { value: "pending", label: "Para confirmar", count: pendingCount.value },
  { value: "reviewed", label: "Confirmados", count: gate.value.reviewed.length },
]);
const summary = computed(() => cleanSummary(gate.value.clean));
const closers = computed(() => closersSummary(gate.value.clean));
const released = computed(() => alertsReleased(gate.value.clean));
const CHIP_LIMIT = 4;
const cleanChips = computed(() =>
  showAllClean.value
    ? gate.value.clean
    : gate.value.clean.slice(0, CHIP_LIMIT),
);
const hiddenClean = computed(() =>
  Math.max(0, gate.value.clean.length - cleanChips.value.length),
);

function matchesQuery(order: QCOrderCardProjection): boolean {
  const q = (props.query ?? "").trim().toLowerCase();
  if (!q) return true;
  return (
    order.recipe_name.toLowerCase().includes(q) ||
    order.output_sku.toLowerCase().includes(q) ||
    order.ref.toLowerCase().includes(q)
  );
}
const shownExceptions = computed(() => gate.value.exceptions.filter(matchesQuery));
const shownReviewed = computed(() => gate.value.reviewed.filter(matchesQuery));

function segments(order: QCOrderCardProjection) {
  return exceptionSegments(order, props.grades, props.defects);
}

function segmentTotal(order: QCOrderCardProjection): number {
  return segments(order).reduce((total, segment) => total + segment.quantity, 0);
}

const SEGMENT_CLASS = {
  standard: "bg-success",
  discount: "bg-warning",
  loss: "bg-destructive",
} as const;
const SEGMENT_TEXT = {
  standard: "text-foreground",
  discount: "text-warning",
  loss: "text-destructive",
} as const;

function oneReleased(order: QCOrderCardProjection): number {
  return order.alert_waiting_count ?? 0;
}

function closedLine(order: QCOrderCardProjection): string {
  const who = order.closed_by ? ` · fechado por ${order.closed_by}` : "";
  const when = order.closed_at_display ? ` ${order.closed_at_display}` : "";
  return `Lote ${order.ref}${who}${when}`;
}

</script>

<template>
  <div class="grid grid-cols-1 gap-4" data-quality-gate>
    <NuxtTabs
      v-if="!hideTabs"
      v-model="view"
      :items="viewTabs"
      :content="false"
      variant="pill"
      class="w-full sm:w-auto sm:justify-self-end"
      aria-label="Lotes da Qualidade"
    >
      <template #trailing="{ item }"><OperatorCountChip :count="item.count" /></template>
    </NuxtTabs>

    <div
      v-if="view === 'pending'"
      class="grid grid-cols-1 items-start gap-6 lg:grid-cols-2"
    >
      <!-- Coluna 1: o conjunto sem exceção (um ato) e os lotes fora do portão. -->
      <section class="grid grid-cols-1 gap-3" aria-labelledby="quality-clean-heading">
        <h2
          id="quality-clean-heading"
          class="op-eyebrow text-muted-foreground"
        >
          Sem exceção
          <span class="tabular-nums">{{ gate.clean.length }}</span>
        </h2>

        <div
          v-if="gate.clean.length"
          class="grid min-w-0 grid-cols-1 gap-4 rounded-xl border-2 border-primary bg-card p-5"
          data-quality-clean
        >
          <div class="flex items-start gap-3">
            <span
              class="grid size-12 shrink-0 place-items-center rounded-full bg-success/15 text-success"
            >
              <Icon name="lucide:check-check" class="size-6" />
            </span>
            <div class="min-w-0">
              <p class="op-display leading-tight">
                {{ plural(gate.clean.length, "lote", "lotes") }}
                {{ isToday ? "de hoje " : "" }}sem exceção
              </p>
              <p class="mt-1 op-body text-muted-foreground">
                {{ summary }}
              </p>
            </div>
          </div>

          <div class="grid gap-2 rounded-lg bg-muted/50 p-3">
            <ul class="flex flex-wrap gap-2" aria-label="Lotes sem exceção">
              <li
                v-for="order in cleanChips"
                :key="order.pk"
                class="inline-flex min-h-8 items-center gap-2 rounded-full border border-border bg-card px-3.5 op-label font-semibold"
              >
                {{ order.recipe_name }}
                <span class="tabular-nums text-muted-foreground">{{
                  lotQuantityLabel(order.full_price_qty, order.output_unit)
                }}</span>
              </li>
              <li
                v-if="hiddenClean"
                class="inline-flex min-h-8 items-center rounded-full border border-border bg-card px-3.5 op-label tabular-nums text-muted-foreground"
              >
                +{{ hiddenClean }}
              </li>
            </ul>
            <NuxtButton
              v-if="gate.clean.length > CHIP_LIMIT"
              color="neutral"
              variant="ghost"
              class="justify-self-start"
              :label="showAllClean ? 'Mostrar menos' : `Ver os ${gate.clean.length} lotes`"
              :trailing-icon="showAllClean ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
              :aria-expanded="showAllClean"
              @click="showAllClean = !showAllClean"
            />
          </div>

          <!-- A consequência antes do gesto: quem fechou e quem será avisado. -->
          <div class="grid gap-3 sm:grid-cols-2">
            <div
              v-if="closers.names"
              class="rounded-lg border border-border p-3"
              data-quality-closers
            >
              <p class="text-xs text-muted-foreground">Fechados por</p>
              <p class="font-semibold">{{ closers.names }}</p>
              <p v-if="closers.window" class="text-sm text-muted-foreground">
                {{ closers.window }}
              </p>
            </div>
            <div
              v-if="released"
              class="rounded-lg border border-border p-3"
              data-quality-released
            >
              <p class="text-xs text-muted-foreground">Ao confirmar</p>
              <template v-if="released.people > 0">
                <p class="flex items-center gap-1.5 font-semibold">
                  <Icon name="lucide:bell-ring" class="size-4" />
                  até {{ plural(released.people, "cliente avisado", "clientes avisados") }}
                </p>
                <p class="text-sm text-muted-foreground">
                  “Me avise” de
                  {{ plural(released.products, "produto", "produtos") }}
                </p>
              </template>
              <p v-else class="font-semibold">
                Nenhum cliente esperando no “Me avise”
              </p>
            </div>
          </div>

          <div class="grid gap-2">
            <NuxtButton
              size="xl"
              block
              class="h-auto whitespace-normal"
              icon="i-lucide-badge-check"
              :label="submitting ? 'Confirmando…' : batchConfirmLabel(gate.clean.length)"
              :disabled="!batchAvailable || submitting"
              :aria-busy="submitting"
              data-quality-confirm-batch
              @click="emit('confirm-batch')"
            />
            <p class="text-center text-sm text-muted-foreground">
              Você confirma como responsável pela qualidade. Fica registrado com
              seu nome.
            </p>
          </div>
        </div>

        <p
          v-else
          class="rounded-lg border border-dashed p-5 text-sm text-muted-foreground"
        >
          Nenhum lote sem exceção esperando confirmação.
        </p>

        <!-- Lote não fechado não entra no portão; o atalho leva aonde se fecha. -->
        <div
          v-if="gate.openCount"
          class="flex items-center justify-between gap-3 rounded-xl border border-dashed border-border p-4"
          data-quality-open
        >
          <p class="flex items-start gap-2 text-sm text-muted-foreground">
            <Icon name="lucide:flame" class="mt-0.5 size-4 shrink-0" />
            <span>
              {{
                plural(
                  gate.openCount,
                  "lote ainda no forno ou sem fechar. Entra",
                  "lotes ainda no forno ou sem fechar. Entram",
                )
              }}
              aqui depois do Fechamento.
            </span>
          </p>
          <NuxtButton
            color="neutral"
            variant="ghost"
            class="shrink-0"
            label="Fechamento"
            trailing-icon="i-lucide-arrow-right"
            @click="emit('go-close')"
          />
        </div>
      </section>

      <!-- Coluna 2: exceções, uma a uma. -->
      <section class="grid grid-cols-1 gap-3" aria-labelledby="quality-exceptions-heading">
        <h2
          id="quality-exceptions-heading"
          class="op-eyebrow text-muted-foreground"
        >
          Exceções para olhar
          <span class="tabular-nums">{{ gate.exceptions.length }}</span>
        </h2>

        <article
          v-for="order in shownExceptions"
          :key="order.pk"
          class="grid min-w-0 grid-cols-1 gap-3 rounded-xl border border-border bg-card p-4"
          data-quality-exception
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate text-lg font-semibold tracking-[-0.01em]">
                {{ order.recipe_name }}
              </p>
              <p class="truncate text-sm text-muted-foreground">
                {{ closedLine(order) }}
              </p>
            </div>
            <NuxtBadge
              color="warning"
              class="shrink-0"
              :label="exceptionBadge(order)"
              data-quality-exception-badge
            />
          </div>

          <div
            class="flex h-2.5 w-full overflow-hidden rounded-full bg-muted"
            role="img"
            :aria-label="segments(order).map((segment) => segment.label).join(', ')"
          >
            <span
              v-for="(segment, index) in segments(order)"
              :key="index"
              :class="SEGMENT_CLASS[segment.kind]"
              :style="{
                width: `${(segment.quantity / Math.max(1, segmentTotal(order))) * 100}%`,
              }"
            />
          </div>
          <ul class="flex flex-wrap justify-between gap-x-4 gap-y-1 text-sm">
            <li
              v-for="(segment, index) in segments(order)"
              :key="index"
              class="tabular-nums"
              :class="SEGMENT_TEXT[segment.kind]"
            >
              {{ segment.label }}
            </li>
          </ul>

          <p class="flex items-start gap-1.5 text-sm text-muted-foreground">
            <Icon name="lucide:info" class="mt-0.5 size-4 shrink-0" />
            <span>
              {{ exceptionReference(order) }}
              <template v-if="oneReleased(order) > 0">
                Ao confirmar, até
                {{ plural(oneReleased(order), "cliente", "clientes") }} do “Me
                avise” recebem o aviso.
              </template>
            </span>
          </p>

          <div class="grid grid-cols-[auto_minmax(0,1fr)] gap-2">
            <NuxtButton
              color="neutral"
              variant="outline"
              size="xl"
              icon="i-lucide-pencil"
              label="Corrigir"
              :disabled="!correctionAvailable(order)"
              :aria-label="`Corrigir a qualidade do lote de ${order.recipe_name}`"
              @click="emit('correct', order)"
            />
            <NuxtButton
              size="xl"
              block
              icon="i-lucide-check"
              :label="submitting ? 'Confirmando…' : 'Confirmar assim'"
              :disabled="!reviewAvailable(order) || submitting"
              :aria-busy="submitting"
              :aria-label="`Confirmar a qualidade do lote de ${order.recipe_name} assim`"
              @click="emit('confirm-one', order)"
            />
          </div>
        </article>

        <p
          v-if="!gate.exceptions.length"
          class="rounded-lg border border-dashed p-5 text-sm text-muted-foreground"
        >
          Nenhuma exceção para olhar.
        </p>

        <p class="flex items-start gap-1.5 text-sm text-muted-foreground">
          <Icon name="lucide:info" class="mt-0.5 size-4 shrink-0" />
          <span>
            Exceção é lote com perda, desconto, outro grau ou contagem diferente
            do que entrou no forno. Corrigir reclassifica o estoque e pede
            motivo.
          </span>
        </p>
      </section>
    </div>

    <div v-else class="grid gap-2" data-quality-reviewed>
      <p
        v-if="!gate.reviewed.length"
        class="py-10 text-center text-muted-foreground"
      >
        Nenhum lote confirmado nesta data.
      </p>
      <div
        v-for="order in shownReviewed"
        :key="order.pk"
        class="flex items-center justify-between gap-3 rounded-md border bg-card p-4"
      >
        <div class="min-w-0">
          <p class="truncate text-base font-semibold">
            {{ order.recipe_name }}
          </p>
          <p class="truncate text-sm text-muted-foreground">
            {{ reviewedSummary(order) }}
          </p>
          <p class="text-xs font-medium text-success">
            Qualidade revisada
            <template v-if="order.correction_count">
              ·
              {{ plural(order.correction_count, "correção", "correções") }}
              <template v-if="order.last_correction_at_display">
                · {{ order.last_correction_at_display }}
              </template>
            </template>
          </p>
        </div>
        <NuxtButton
          v-if="correctionAvailable(order)"
          color="neutral"
          variant="outline"
          class="shrink-0"
          icon="i-lucide-pencil"
          label="Corrigir"
          :aria-label="`Corrigir a qualidade do lote de ${order.recipe_name}`"
          @click="emit('correct', order)"
        />
      </div>
    </div>
  </div>
</template>
