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
  exceptionBadge,
  exceptionReference,
  exceptionSegments,
  lotQuantityLabel,
  plural,
  qualityGate,
  reviewedSummary,
} from "~/presentation/qualityGate";
import { formatClock } from "../../../operator-kit/app/presentation/clock";

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
// Quem não pode confirmar nem corrigir não vê botões mortos nem a promessa
// "Você confirma como responsável" (beta 05/11): vê quem confirma.
const MANAGER_ONLY_TEXT = "Quem confirma a qualidade é o gerente. Chame quem está de turno.";
const managerOnly = computed(
  () => props.orders.length > 0 && props.orders.every((order) => !order.can_correct),
);
const pendingCount = computed(
  () => gate.value.clean.length + gate.value.exceptions.length,
);
const viewTabs = computed(() => [
  { value: "pending", label: "Para confirmar", count: pendingCount.value },
  { value: "reviewed", label: "Confirmados", count: gate.value.reviewed.length },
]);
const released = computed(() => alertsReleased(gate.value.clean));

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
  const who = order.closed_by ? ` · finalizado por ${order.closed_by}` : "";
  const when = order.closed_at_display ? ` ${formatClock(order.closed_at_display)}` : "";
  // KISS (dono, 28/11): o código do lote é da Gerente no detalhe, não do chão.
  return `${who}${when}`.replace(/^ · /, "");
}

</script>

<template>
  <div class="grid grid-cols-1 gap-4" data-quality-gate>
    <!-- Quem não confirma lê UMA vez quem confirma, no topo; os cartões não repetem. -->
    <p
      v-if="managerOnly && view === 'pending' && pendingCount"
      class="flex items-center gap-2 rounded-lg bg-muted/50 px-4 py-3 op-body text-muted-foreground"
      data-quality-manager-only
    >
      <Icon name="lucide:user-check" class="size-4 shrink-0" aria-hidden="true" />
      {{ MANAGER_ONLY_TEXT }}
    </p>
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
        <h2 id="quality-clean-heading" class="sr-only">Sem exceção</h2>

        <div
          v-if="gate.clean.length"
          class="grid min-w-0 grid-cols-1 gap-4 rounded-xl border-2 border-primary bg-card p-5"
          data-quality-clean
        >
          <!-- KISS (dono, 28/11): "16 lotes sem exceção [Ver] [Confirmar]". A lista
               abre no Ver; quem finalizou e o "Me avise" vazio saíram (o aviso a
               clientes, quando há, fica: é a consequência do gesto). -->
          <div class="flex flex-wrap items-center justify-between gap-3">
            <p class="op-title">
              {{ plural(gate.clean.length, "lote", "lotes") }} sem exceção
            </p>
            <NuxtButton
              color="neutral"
              variant="outline"
              :label="showAllClean ? 'Ocultar' : 'Ver'"
              :trailing-icon="showAllClean ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
              :aria-expanded="showAllClean"
              data-quality-clean-toggle
              @click="showAllClean = !showAllClean"
            />
          </div>

          <div v-if="showAllClean" class="rounded-lg bg-muted/50 p-3">
            <ul class="flex flex-wrap gap-2" aria-label="Lotes sem exceção">
              <li
                v-for="order in gate.clean"
                :key="order.pk"
                class="inline-flex min-h-8 items-center gap-2 rounded-full border border-border bg-card px-3.5 op-label font-semibold"
              >
                {{ order.recipe_name }}
                <span class="tabular-nums text-muted-foreground">{{
                  lotQuantityLabel(order.full_price_qty, order.output_unit)
                }}</span>
              </li>
            </ul>
          </div>

          <p
            v-if="released && released.people > 0"
            class="flex items-center gap-2 op-body"
            data-quality-released
          >
            <Icon name="lucide:bell-ring" class="size-4 shrink-0" aria-hidden="true" />
            Ao confirmar, até
            {{ plural(released.people, "cliente do “Me avise” é avisado", "clientes do “Me avise” são avisados") }}.
          </p>

          <div v-if="!managerOnly" class="grid gap-2">
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

        <!-- Lote não finalizado não entra no portão; o atalho leva à Finalização. -->
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
                  "lote ainda no forno ou sem finalizar. Entra",
                  "lotes ainda no forno ou sem finalizar. Entram",
                )
              }}
              aqui depois da Finalização.
            </span>
          </p>
          <NuxtButton
            color="neutral"
            variant="ghost"
            class="shrink-0"
            label="Finalização"
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
              <p v-if="closedLine(order)" class="truncate text-sm text-muted-foreground">
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

          <p class="text-sm text-muted-foreground">
            <span>
              {{ exceptionReference(order) }}
              <template v-if="oneReleased(order) > 0">
                Ao confirmar, até
                {{ plural(oneReleased(order), "cliente", "clientes") }} do “Me
                avise” recebem o aviso.
              </template>
            </span>
          </p>

          <div v-if="!managerOnly" class="grid grid-cols-[auto_minmax(0,1fr)] gap-2">
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
