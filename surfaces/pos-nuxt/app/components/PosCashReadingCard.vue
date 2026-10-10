<script setup lang="ts">
// Leitura de turno (X aberto, Z fechado) do relatório da antesala.
// BLIND: renderiza só o que a projection serve — abertura, movimentos, vendas
// por método e (no Z) o valor CONTADO. O esperado da gaveta não existe aqui.
//
// Fase 2 (onda do PDV): a leitura é uma SEÇÃO, não um cartão. Os números do turno
// moram num cartão e cada lista na tabela da suíte (`OperatorTable`, que já é o seu
// cartão): cartão dentro de cartão era o que a leitura antiga desenhava.
import { movementFlow, readingTitle, shiftPeriodDisplay, signedMovementDisplay } from "~/presentation/cashReport";
import type { ShiftReading } from "~/types/cashReport";

const props = defineProps<{
  reading: ShiftReading;
  /** A porta da segunda via existe? Quem a abre é a página (write-side). */
  canReprint?: boolean;
  busy?: boolean;
}>();

// A segunda via é pedida pela LINHA do livro — a página chama o endpoint com
// `?reprint=1` e o papel sai marcado como segunda via.
const emit = defineEmits<{ reprint: [entryId: number] }>();

const period = computed(() => shiftPeriodDisplay(props.reading));
const isOpen = computed(() => props.reading.status === "open");

const NUM = { class: { th: "text-right", td: "text-right tabular-nums whitespace-nowrap" } };
const methodColumns = [
  { accessorKey: "method_label", header: "Método" },
  { accessorKey: "orders_count", header: "Pagamentos", meta: NUM },
  { id: "amount", header: "Valor", meta: NUM },
];
const movementColumns = computed(() => [
  { accessorKey: "kind_label", header: "Tipo" },
  { id: "reason", header: "Motivo" },
  { id: "amount", header: "Valor", meta: NUM },
  ...(props.canReprint ? [{ id: "reprint", header: "Comprovante", meta: { class: { th: "text-right", td: "text-right" } } }] : []),
]);
</script>

<template>
  <section class="grid gap-3" :aria-label="readingTitle(reading)" data-cash-reading>
    <div class="flex flex-wrap items-center gap-2">
      <Icon :name="isOpen ? 'lucide:receipt-text' : 'lucide:archive'" class="size-4 text-muted-foreground" />
      <h2 class="text-base font-semibold">{{ readingTitle(reading) }}</h2>
      <NuxtBadge v-if="isOpen" color="success" label="Turno aberto · parcial" />
      <span class="text-sm text-muted-foreground sm:ml-auto">
        {{ reading.operator }} · {{ reading.terminal_label }}<template v-if="period"> · {{ period }}</template>
      </span>
    </div>

    <NuxtCard>
      <dl class="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div class="flex flex-col">
          <dt class="text-xs text-muted-foreground">Abertura</dt>
          <dd class="font-medium tabular-nums">R$ {{ reading.opening_amount_display }}</dd>
        </div>
        <div class="flex flex-col">
          <dt class="text-xs text-muted-foreground">Vendas</dt>
          <dd class="font-medium tabular-nums">{{ reading.sales_count }}</dd>
        </div>
        <div class="flex flex-col">
          <dt class="text-xs text-muted-foreground">Total vendido</dt>
          <dd class="font-medium tabular-nums">R$ {{ reading.sales_total_display }}</dd>
        </div>
        <div v-if="!isOpen" class="flex flex-col">
          <dt class="text-xs text-muted-foreground">Contado no fechamento</dt>
          <dd class="font-medium tabular-nums">R$ {{ reading.counted_amount_display }}</dd>
        </div>
      </dl>
    </NuxtCard>

    <div class="grid gap-2">
      <h3 class="text-sm font-medium">Vendas por método</h3>
      <p v-if="!reading.sales_by_method.length" class="text-sm text-muted-foreground">
        Nenhum pagamento registrado no turno.
      </p>
      <OperatorTable
        v-else
        :data="reading.sales_by_method"
        :columns="methodColumns"
        :row-key="(row) => row.method"
        :caption="`Vendas por método: ${readingTitle(reading)}`"
      >
        <template #amount-cell="{ row }">R$ {{ row.original.amount_display }}</template>
      </OperatorTable>
    </div>

    <div class="grid gap-2">
      <h3 class="text-sm font-medium">Movimentos de gaveta</h3>
      <p v-if="!reading.movements.length" class="text-sm text-muted-foreground">
        Nenhum movimento manual no turno.
      </p>
      <OperatorTable
        v-else
        :data="reading.movements"
        :columns="movementColumns"
        :row-key="(row) => String(row.entry_id)"
        :caption="`Movimentos de gaveta: ${readingTitle(reading)}`"
      >
        <template #reason-cell="{ row }">
          <span class="text-muted-foreground">{{ row.original.reason || "Sem motivo informado" }}</span>
        </template>
        <template #amount-cell="{ row }">
          <span :class="movementFlow(row.original) === 'out' ? 'text-error' : 'text-success'">
            {{ signedMovementDisplay(row.original) }}
          </span>
        </template>
        <template #reprint-cell="{ row }">
          <NuxtButton
            color="neutral"
            variant="ghost"
            icon="i-lucide-printer"
            label="Segunda via"
            :disabled="props.busy"
            :aria-label="`Imprimir segunda via do comprovante de ${row.original.kind_label.toLowerCase()}`"
            @click="emit('reprint', row.original.entry_id)"
          />
        </template>
      </OperatorTable>
      <p class="text-xs text-muted-foreground">
        Entradas: R$ {{ reading.movements_in_display }} · Saídas: R$ {{ reading.movements_out_display }}
      </p>
    </div>

    <p v-if="reading.notes" class="text-sm text-muted-foreground">
      Observações: {{ reading.notes }}
    </p>
  </section>
</template>
