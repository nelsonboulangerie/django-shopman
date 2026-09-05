<script setup lang="ts">
import type {
  ConversionKind,
  Material,
  MaterialConversion,
  ReceiptFieldAnchor,
  ReceiptLine,
  ReceiptLinePreview,
  ReceiptWarningTone,
} from "~/types/purchase";
import { formatMoney, formatQty, receiptLineLabel, receiptLineStatus, receiptLineStatusBadge } from "~/presentation/purchase";
import { RECEIPT_LINE_STATUS_BADGE } from "~/utils/receiptLineStatus";
import { FLASH_RING } from "~/utils/receiptFocus";

/**
 * UM item da entrada, aberto por inteiro — e o nome dele SEMPRE à vista.
 *
 * A lista lá fora é para enxergar a nota toda; aqui é para mexer num item só.
 * Por isso o cabeçalho não rola: numa gaveta com insumo, embalagem, quantidade,
 * validade e lote, o operador rola até o meio e perde de vista em qual das dez
 * linhas da nota ele está. O título fixo é o que responde "qual item é este?"
 * sem que ele precise fechar e abrir de novo.
 *
 * Conferir é o gesto que FECHA a gaveta: o item se resolve e a lista atrás
 * muda de cor sozinha. É o retorno do gesto, no lugar onde o olho já está.
 *
 * ⚠️ O `MaterialPicker` daqui de dentro tem véu próprio (`fixed inset-0`) e
 * engole o `Esc` (`stopPropagation`), de propósito: sem isso o `Esc` que fecha
 * a lista de insumos atravessaria e fecharia a gaveta inteira junto.
 */
const props = defineProps<{
  open: boolean;
  /** `null` enquanto nenhum item está aberto — a gaveta não monta formulário vazio. */
  preview: ReceiptLinePreview | null;
  materials: Material[];
  /** Só as conversões do insumo deste item. */
  conversions: MaterialConversion[];
  pending?: boolean;
  /** Quanto fica no estoque depois desta entrada, na unidade-base do insumo. */
  stockAfter: number;
  /** O campo que a tela acabou de apontar — ganha o anel âmbar por alguns segundos. */
  flashField?: ReceiptFieldAnchor | null;
}>();

const emit = defineEmits<{
  "update:open": [open: boolean];
  update: [patch: Partial<ReceiptLine>];
  selectMaterial: [sku: string];
  acceptSuggestion: [];
  selectConversion: [conversionId: string | null];
  acceptConversion: [];
  acceptAxes: [];
  declareConversion: [input: { label: string; factor: string; kind: ConversionKind }];
  check: [checked: boolean];
  remove: [];
}>();

const label = computed(() => (props.preview ? receiptLineLabel(props.preview) : ""));
const status = computed(() => (props.preview ? receiptLineStatus(props.preview) : "ready"));
const badge = computed(() => receiptLineStatusBadge(status.value));

/**
 * Os campos de digitar continuam com `v-model`, e não com `:value`/`@input`.
 *
 * Não é preguiça: a diretiva do `v-model` sabe não sobrescrever o que está
 * sendo digitado (`1,` a caminho de `1,5`), e uma ligação de atributo à mão
 * apaga o dígito no meio da digitação. O `set` de cada um manda o patch para
 * quem é dono da linha — mutar a prop aqui dentro seria escrever no rascunho
 * pelas costas do composable.
 */
function lineField<K extends keyof ReceiptLine>(key: K, fallback: ReceiptLine[K]) {
  return computed({
    get: () => (props.preview ? props.preview.line[key] : fallback),
    set: (value: ReceiptLine[K]) => emit("update", { [key]: value } as Partial<ReceiptLine>),
  });
}

const purchaseQty = lineField("purchaseQty", 0);
const costInput = lineField("costInput", "");
const expiryDate = lineField("expiryDate", "");
const invoiceLot = lineField("invoiceLot", "");
const lineNote = lineField("lineNote", "");

/** O aviso que o cabeçalho já diz não se repete embaixo. */
const visibleWarnings = computed(() =>
  props.preview ? props.preview.warnings.filter((warning) => warning.label !== props.preview!.nextStep) : [],
);

const warningClasses: Record<ReceiptWarningTone, string> = {
  ok: "border-success/25 bg-success/10 text-success",
  watch: "border-warning/30 bg-warning/10 text-warning",
  block: "border-destructive/30 bg-destructive/10 text-destructive",
};

function ring(field: ReceiptFieldAnchor): string {
  return props.flashField === field ? FLASH_RING : "";
}

/** Conferir fecha a gaveta; desmarcar mantém aberta, porque ainda há o que ver. */
function onCheck(checked: boolean) {
  emit("check", checked);
  if (checked) emit("update:open", false);
}
</script>

<template>
  <UiSheet :open="open" @update:open="emit('update:open', $event)">
    <UiSheetContent
      v-if="preview"
      :data-receipt-sheet="preview.line.id"
      side="right"
      class="w-full sm:max-w-xl"
    >
      <!-- O TÍTULO NÃO ROLA. É a promessa desta tela: o operador rola o
           formulário inteiro e continua sabendo em qual item está. -->
      <UiSheetHeader class="shrink-0 gap-2 border-b border-border bg-card p-4">
        <div class="flex items-start justify-between gap-2">
          <span
            class="inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-xs font-semibold"
            :class="RECEIPT_LINE_STATUS_BADGE[status]"
          >
            <Icon :name="badge.icon" class="size-3.5" />
            {{ badge.label }}
          </span>
          <!-- Fechar é o PRIMEIRO controle da gaveta, e não por estética: ao
               abrir, o foco pousa no primeiro botão de dentro. Com a lixeira
               aqui, um Enter distraído apagaria o item da nota. Remover mora no
               rodapé, longe do gesto automático. -->
          <UiSheetX />
        </div>
        <UiSheetTitle class="text-base leading-snug">{{ label }}</UiSheetTitle>
        <UiSheetDescription>
          {{ preview.invoiceSummary || "Lançado à mão, sem documento fiscal." }}
        </UiSheetDescription>
        <p
          v-if="preview.nextStep"
          class="flex items-center gap-1.5 rounded-md bg-warning/10 px-2 py-1.5 text-xs font-medium text-warning"
        >
          <Icon name="lucide:arrow-right" class="size-3.5 shrink-0" />
          {{ preview.nextStep }}
        </p>
      </UiSheetHeader>

      <!-- O corpo rola por baixo do cabeçalho. -->
      <div class="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        <div v-if="preview.line.invoiceTotal" class="flex items-center justify-between gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm">
          <span class="text-xs font-medium text-muted-foreground">Valor na nota</span>
          <span class="font-semibold tabular-nums">{{ preview.line.invoiceTotal }}</span>
        </div>

        <!-- 1. Qual insumo é. Quando há sugestão, o campo INTEIRO entra num card
             de atenção: a proposta fica colada ao campo de que ela fala. -->
        <ReceiptField
          data-receipt-field="material"
          class="scroll-mt-4 transition-shadow"
          :class="ring('material')"
          :attention="Boolean(preview.suggestion) || (!preview.line.materialSku && !preview.suggestion)"
          :title="preview.suggestion ? 'Confirme a sugestão' : 'Escolha o insumo desta linha'"
          :icon="preview.suggestion ? 'lucide:sparkles' : 'lucide:package-search'"
        >
          <!-- O rótulo é um `<span>`, NÃO um `<label>`: um `<label>` sem `for`
               adota o primeiro controle rotulável de dentro (o botão que abre o
               MaterialPicker) e reencaminha para ele os cliques que caem em
               parte não interativa — inclusive o véu de fechar do próprio
               picker. Escolher o insumo fechava e reabria a lista no mesmo
               clique. O nome acessível vai por `labelledBy`. -->
          <div>
            <span :id="`receipt-material-${preview.line.id}`" class="block text-xs font-medium text-muted-foreground">Insumo</span>
            <MaterialPicker
              class="mt-1"
              :materials="materials"
              :model-value="preview.line.materialSku"
              :labelled-by="`receipt-material-${preview.line.id}`"
              @update:model-value="emit('selectMaterial', $event)"
            />
          </div>
          <template v-if="preview.suggestion">
            <p class="mt-2 text-xs text-muted-foreground">
              Parece <span class="font-medium text-foreground">{{ preview.suggestion.name }}</span> ({{ preview.suggestion.scorePercent }}% parecido)
            </p>
            <button type="button" class="mt-2 inline-flex h-11 w-full items-center justify-center gap-1.5 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground sm:w-auto" @click="emit('acceptSuggestion')">
              <Icon name="lucide:check" class="size-3.5" />
              É este
            </button>
          </template>
        </ReceiptField>

        <!-- 2. Só depois do insumo: quanto isso vale na unidade dele. Pedir
             conversão antes de saber o insumo é pedir o impossível — não há
             unidade-base para converter PARA. -->
        <div v-if="preview.line.materialSku" data-receipt-field="conversion" class="scroll-mt-4 transition-shadow" :class="ring('conversion')">
          <ReceiptConversion
            :preview="preview"
            :conversions="conversions"
            :pending="pending"
            @select="emit('selectConversion', $event)"
            @accept="emit('acceptConversion')"
            @accept-axes="emit('acceptAxes')"
            @declare="emit('declareConversion', $event)"
          />
        </div>

        <!-- 3. Quanto e quanto custou. O custo por unidade-base mora COM o
             valor, porque é dele que ele deriva. -->
        <div data-receipt-field="qty" class="grid scroll-mt-4 gap-3 transition-shadow sm:grid-cols-2" :class="ring('qty')">
          <label class="block text-xs font-medium text-muted-foreground">
            Quantidade{{ preview.purchaseUnitLabel ? ` (${preview.purchaseUnitLabel})` : "" }}
            <input v-model.number="purchaseQty" type="number" min="0" step="0.01" class="mt-1 h-11 w-full rounded-md border border-border bg-card px-3 text-sm tabular-nums text-foreground" />
          </label>
          <label class="block text-xs font-medium text-muted-foreground">
            Valor total (R$)
            <input v-model="costInput" inputmode="decimal" class="mt-1 h-11 w-full rounded-md border border-border bg-card px-3 text-sm tabular-nums text-foreground" placeholder="0,00" />
            <span v-if="preview.baseQtyKnown && preview.baseCostQ > 0" class="mt-1 block text-xs font-normal text-muted-foreground">
              {{ formatMoney(preview.baseCostQ) }} por {{ preview.material.unit }}
            </span>
          </label>
        </div>

        <!-- 4. De onde veio e até quando vale. Os dois saem do mesmo grupo
             `rastro` da NF-e e respondem à mesma pergunta. -->
        <ReceiptField
          data-receipt-field="expiry"
          class="scroll-mt-4 transition-shadow"
          :class="ring('expiry')"
          :attention="preview.needsExpiry"
          title="Informe a validade"
          icon="lucide:calendar-clock"
        >
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="block text-xs font-medium text-muted-foreground">
              Validade
              <input v-model="expiryDate" type="date" class="mt-1 h-11 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground" />
              <span v-if="preview.line.expiryFromInvoice" class="mt-1 block text-xs font-normal text-muted-foreground">Veio na nota</span>
              <span v-else-if="preview.needsExpiry" class="mt-1 block text-xs font-normal text-muted-foreground">A nota não informou. Olhe na embalagem.</span>
            </label>
            <label class="block text-xs font-medium text-muted-foreground">
              Lote do fornecedor
              <input v-model="invoiceLot" class="mt-1 h-11 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground" placeholder="Opcional" />
              <span v-if="preview.line.invoiceLot" class="mt-1 block text-xs font-normal text-muted-foreground">É por ele que um recall chama.</span>
            </label>
          </div>
        </ReceiptField>

        <!-- 5. O que entra no estoque, e a consequência disso. -->
        <div class="rounded-md border border-border bg-card px-3 py-2">
          <template v-if="preview.baseQtyKnown && preview.line.materialSku">
            <p class="text-lg font-semibold tabular-nums">Entra {{ formatQty(preview.baseQty, preview.material.unit) }}</p>
            <p class="mt-0.5 text-xs text-muted-foreground">
              Estoque depois: {{ formatQty(stockAfter, preview.material.unit) }}
            </p>
          </template>
          <p v-else class="text-sm text-muted-foreground">A entrada aparece aqui quando o insumo e a embalagem estiverem definidos.</p>
        </div>

        <label class="block text-xs font-medium text-muted-foreground">
          Ocorrência
          <input v-model="lineNote" class="mt-1 h-11 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground" placeholder="Avaria, falta, ressalva" />
        </label>

        <div v-if="visibleWarnings.length" class="flex flex-wrap gap-1.5">
          <span
            v-for="warning in visibleWarnings"
            :key="`${preview.line.id}-${warning.key}`"
            class="rounded-md border px-2 py-0.5 text-xs font-medium"
            :class="warningClasses[warning.tone]"
          >
            {{ warning.label }}
          </span>
        </div>
      </div>

      <!-- Conferir fecha o item e a gaveta: o gesto termina onde começou, e a
           linha lá fora muda de cor na frente do operador. -->
      <UiSheetFooter class="shrink-0 border-t border-border">
        <button
          v-if="!preview.line.checked"
          type="button"
          data-receipt-field="check"
          class="inline-flex h-12 w-full scroll-mt-4 items-center justify-center gap-2.5 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground transition-shadow"
          :class="ring('check')"
          @click="onCheck(true)"
        >
          <Icon name="lucide:circle-check-big" class="size-5 shrink-0" />
          Marcar como conferido
        </button>
        <button
          v-else
          type="button"
          data-receipt-field="check"
          class="inline-flex h-12 w-full scroll-mt-4 items-center justify-center gap-2.5 rounded-md border border-success/40 bg-success/10 px-3 text-sm font-semibold text-success transition-shadow"
          :class="ring('check')"
          @click="onCheck(false)"
        >
          <Icon name="lucide:circle-check-big" class="size-5 shrink-0" />
          Conferido — desmarcar
        </button>
        <UiSheetClose class="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md border border-border bg-card px-3 text-sm font-medium hover:bg-accent">
          {{ preview.line.checked ? "Fechar" : "Fechar sem conferir" }}
        </UiSheetClose>
        <button
          type="button"
          class="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md px-3 text-sm font-medium text-destructive hover:bg-destructive/10"
          :aria-label="`Remover ${label}`"
          @click="emit('remove')"
        >
          <Icon name="lucide:trash-2" class="size-4" />
          Remover item da entrada
        </button>
      </UiSheetFooter>
    </UiSheetContent>
  </UiSheet>
</template>
