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
import { ref, watch } from "vue";
import { createReusableTemplate } from "@vueuse/core";
import {
  formatMoney,
  formatQty,
  receiptLineDifference,
  receiptLineLabel,
  receiptLineStatus,
  receiptLineStatusBadge,
} from "~/presentation/purchase";
import { RECEIPT_LINE_STATUS_BADGE } from "~/utils/receiptLineStatus";
import { FLASH_RING } from "~/utils/receiptFocus";
import { todayIso as todayIsoDate } from "../../../operator-kit/app/presentation/dates";

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
 * ⚠️ O `UiSelect` daqui de dentro tem véu próprio (`fixed inset-0`) e engole o
 * `Esc` (`stopPropagation`), de propósito: sem isso o `Esc` que fecha a lista de
 * insumos atravessaria e fecharia a gaveta inteira junto.
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
  /**
   * Tablet (C09): a gaveta encaixada ao lado da lista, sem véu por cima. A lista
   * continua tocável e o item vizinho abre sem fechar a gaveta (‹ ›).
   */
  docked?: boolean;
  /** "Item 1 de 7" e as setas ‹ › da gaveta encaixada. */
  position?: { index: number; total: number } | null;
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
  step: [delta: number];
  "scan-ean": [];
  "read-package": [];
  "reject-line": [];
}>();

const [DefineBody, ReuseBody] = createReusableTemplate();

// ── Numérico na tela (C10, v3 tablet pino 6): o campo ativo recebe os dígitos sem
// o teclado do sistema cobrir metade da gaveta. −1/+1 na quantidade, Limpar, e
// "Valor →" pula da quantidade para o valor total.
type PadField = "qty" | "cost";
const padField = ref<PadField>("qty");
const padFresh = ref(true);
watch(
  () => props.preview?.line.id,
  () => {
    padField.value = "qty";
    padFresh.value = true;
  },
);
function padDigit(digit: string) {
  if (padField.value === "qty") {
    const current = padFresh.value ? "" : String(purchaseQty.value ?? "").replace(".", ",");
    const next = `${current}${digit}`;
    purchaseQty.value = Number(next.replace(",", ".")) || 0;
  } else {
    const current = padFresh.value ? "" : String(costInput.value ?? "");
    costInput.value = `${current}${digit}`;
  }
  padFresh.value = false;
}
function padComma() {
  if (padField.value === "cost") {
    if (!String(costInput.value).includes(",")) costInput.value = `${padFresh.value ? "0" : costInput.value},`;
  }
  padFresh.value = false;
}
function padBackspace() {
  if (padField.value === "qty") {
    const text = String(purchaseQty.value ?? "");
    purchaseQty.value = Number(text.slice(0, -1)) || 0;
  } else {
    costInput.value = String(costInput.value ?? "").slice(0, -1);
  }
  padFresh.value = false;
}
function padClear() {
  if (padField.value === "qty") purchaseQty.value = 0;
  else costInput.value = "";
  padFresh.value = true;
}
function padBump(delta: number) {
  padField.value = "qty";
  purchaseQty.value = Math.max(0, (Number(purchaseQty.value) || 0) + delta);
  padFresh.value = false;
}
function padNext() {
  padField.value = padField.value === "qty" ? "cost" : "qty";
  padFresh.value = true;
}
const hasDifference = computed(() => (props.preview ? Boolean(receiptLineDifference(props.preview.line)) : false));


// O insumo vira opção genérica do `UiSelect`: o SKU e a unidade seguem
// pesquisáveis (é o que o operador lê na etiqueta quando o nome não bate), e a
// categoria entra só na busca, porque na linha ela não caberia.
const materialOptions = computed(() =>
  props.materials.map((material) => ({
    value: material.sku,
    label: material.name,
    hint: `${material.sku} · conta em ${material.unit}`,
    keywords: material.category,
  })),
);

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
const todayIso = todayIsoDate();
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
  <!-- O corpo da gaveta, um só para os dois jeitos (encaixada no tablet, por cima no
       celular e no desktop). O TÍTULO NÃO ROLA: o operador rola o formulário inteiro
       e continua sabendo em qual item está. -->
  <DefineBody>
    <template v-if="preview">
      <header class="shrink-0 space-y-2 border-b border-border bg-card p-4" data-slot="sheet-header">
        <div class="flex items-start justify-between gap-2">
          <div class="flex flex-wrap items-center gap-2">
            <span
              class="inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-semibold"
              :class="RECEIPT_LINE_STATUS_BADGE[status]"
            >
              <Icon :name="badge.icon" class="size-3.5" />
              {{ badge.label }}
            </span>
            <span v-if="position" class="op-micro text-muted-foreground tnum">Item {{ position.index }} de {{ position.total }}</span>
          </div>
          <!-- Encaixada: ‹ › trocam de item sem fechar. Por cima: Fechar é o PRIMEIRO
               controle (o foco pousa nele, nunca na lixeira). -->
          <div v-if="docked" class="flex gap-1.5">
            <button type="button" class="grid size-11 place-items-center rounded-full border border-border hover:bg-accent disabled:opacity-40" aria-label="Item anterior" :disabled="!position || position.index <= 1" @click="emit('step', -1)">
              <Icon name="lucide:chevron-left" class="size-5" />
            </button>
            <button type="button" class="grid size-11 place-items-center rounded-full border border-border hover:bg-accent disabled:opacity-40" aria-label="Próximo item" :disabled="!position || position.index >= position.total" @click="emit('step', 1)">
              <Icon name="lucide:chevron-right" class="size-5" />
            </button>
          </div>
          <UiSheetX v-else placement="inline" />
        </div>
        <!-- Por cima, o título é o do diálogo (leitor de tela); encaixada, um h2. -->
        <h2 v-if="docked" class="text-base leading-snug font-semibold" data-slot="sheet-title">{{ label }}</h2>
        <UiSheetTitle v-else class="text-base leading-snug">{{ label }}</UiSheetTitle>
        <p v-if="docked" class="text-sm text-muted-foreground">
          {{ preview.invoiceSummary || "Lançado à mão, sem documento fiscal." }}
        </p>
        <UiSheetDescription v-else>
          {{ preview.invoiceSummary || "Lançado à mão, sem documento fiscal." }}
        </UiSheetDescription>
        <p
          v-if="preview.nextStep"
          class="flex items-center gap-1.5 rounded-md bg-warning/10 px-2 py-1.5 text-xs font-medium text-warning"
        >
          <Icon name="lucide:arrow-right" class="size-3.5 shrink-0" />
          {{ preview.nextStep }}
        </p>
      </header>

      <!-- O corpo rola por baixo do cabeçalho. -->
      <div class="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        <div v-if="preview.line.invoiceTotal" class="flex items-center justify-between gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm">
          <span class="text-xs font-medium text-muted-foreground">Valor na nota</span>
          <span class="font-semibold tabular-nums">{{ preview.line.invoiceTotal }}</span>
        </div>

        <!-- 1. Qual insumo é, com o EAN pela câmera ao lado (C11). O rótulo é um
             `<span>`, NÃO um `<label>`: ver o docstring do `UiSelect`. -->
        <ReceiptField
          data-receipt-field="material"
          class="scroll-mt-4 transition-shadow"
          :class="ring('material')"
          :attention="Boolean(preview.suggestion) || (!preview.line.materialSku && !preview.suggestion)"
          :title="preview.suggestion ? 'Confirme a sugestão' : 'Escolha o item desta linha'"
          :icon="preview.suggestion ? 'lucide:sparkles' : 'lucide:package-search'"
        >
          <div>
            <span :id="`receipt-material-${preview.line.id}`" class="block text-xs font-medium text-muted-foreground">Item</span>
            <div class="mt-1 flex gap-2">
              <UiSelect
                class="min-w-0 flex-1"
                :options="materialOptions"
                :model-value="preview.line.materialSku"
                :labelled-by="`receipt-material-${preview.line.id}`"
                placeholder="Escolher item"
                search-placeholder="Buscar item do Compras"
                :empty-text="`Nenhum item do Compras com esse nome.`"
                @update:model-value="emit('selectMaterial', $event)"
              />
              <button
                type="button"
                class="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-md border border-border bg-card px-3 text-sm font-semibold hover:bg-accent"
                aria-label="Ler o EAN do item pela câmera"
                data-sheet-scan-ean
                @click="emit('scan-ean')"
              >
                <Icon name="lucide:scan-barcode" class="size-4" />
                EAN
              </button>
            </div>
            <p v-if="preview.line.scannedEan" class="mt-1 text-xs text-muted-foreground tnum">EAN lido: {{ preview.line.scannedEan }}</p>
          </div>
          <template v-if="preview.suggestion">
            <p v-if="preview.suggestion.byBarcode" class="mt-2 text-xs text-muted-foreground">
              O código de barras da nota é o de <span class="font-medium text-foreground">{{ preview.suggestion.name }}</span>
            </p>
            <p v-else class="mt-2 text-xs text-muted-foreground">
              Parece <span class="font-medium text-foreground">{{ preview.suggestion.name }}</span> ({{ preview.suggestion.scorePercent }}% parecido)
            </p>
            <button type="button" class="mt-2 inline-flex h-11 w-full items-center justify-center gap-1.5 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground sm:w-auto" @click="emit('acceptSuggestion')">
              <Icon name="lucide:check" class="size-3.5" />
              É este
            </button>
          </template>
        </ReceiptField>

        <!-- 2. Só depois do insumo: quanto isso vale na unidade dele. -->
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

        <!-- 3. Quanto e quanto custou, com o numérico na tela (C10). O campo ativo
             tem a borda cheia; tocar no outro campo troca o alvo do teclado. -->
        <div data-receipt-field="qty" class="scroll-mt-4 space-y-2 transition-shadow" :class="ring('qty')">
          <div class="grid gap-2 sm:grid-cols-2">
            <button
              type="button"
              class="flex min-h-16 flex-col items-start justify-center rounded-lg border bg-card px-3 py-2 text-left"
              :class="padField === 'qty' ? 'border-2 border-primary' : 'border-border'"
              :aria-pressed="padField === 'qty'"
              data-sheet-qty-field
              @click="padField = 'qty'; padFresh = true"
            >
              <span class="text-xs font-medium text-muted-foreground">Quantidade{{ preview.purchaseUnitLabel ? ` (${preview.purchaseUnitLabel})` : "" }}</span>
              <span class="flex w-full items-baseline justify-between gap-2">
                <span class="text-2xl font-semibold tabular-nums">{{ String(preview.line.purchaseQty ?? 0).replace(".", ",") }}</span>
                <span v-if="preview.baseQtyKnown && preview.line.materialSku" class="text-xs text-muted-foreground tabular-nums">
                  entra {{ formatQty(preview.baseQty, preview.material.unit) }}
                </span>
              </span>
            </button>
            <button
              type="button"
              class="flex min-h-16 flex-col items-start justify-center rounded-lg border bg-card px-3 py-2 text-left"
              :class="padField === 'cost' ? 'border-2 border-primary' : 'border-border'"
              :aria-pressed="padField === 'cost'"
              data-sheet-cost-field
              @click="padField = 'cost'; padFresh = true"
            >
              <span class="text-xs font-medium text-muted-foreground">Valor total (R$)</span>
              <span class="flex w-full items-baseline justify-between gap-2">
                <span class="text-2xl font-semibold tabular-nums">{{ preview.line.costInput || "0,00" }}</span>
                <span v-if="preview.baseQtyKnown && preview.baseCostQ > 0" class="text-xs text-muted-foreground tabular-nums">
                  {{ formatMoney(preview.baseCostQ) }}/{{ preview.material.unit }}
                </span>
              </span>
            </button>
          </div>
          <div class="grid grid-cols-4 gap-1.5" role="group" aria-label="Teclado numérico do item" data-sheet-numpad>
            <template v-for="digit in ['1', '2', '3']" :key="digit">
              <button type="button" class="h-12 rounded-md border bg-card text-lg font-semibold tabular-nums hover:bg-accent" :aria-label="`Dígito ${digit}`" @click="padDigit(digit)">{{ digit }}</button>
            </template>
            <button type="button" class="h-12 rounded-md border border-primary/25 bg-primary/8 text-base font-semibold hover:bg-primary/15" aria-label="Um a menos" @click="padBump(-1)">−1</button>
            <template v-for="digit in ['4', '5', '6']" :key="digit">
              <button type="button" class="h-12 rounded-md border bg-card text-lg font-semibold tabular-nums hover:bg-accent" :aria-label="`Dígito ${digit}`" @click="padDigit(digit)">{{ digit }}</button>
            </template>
            <button type="button" class="h-12 rounded-md border border-primary/25 bg-primary/8 text-base font-semibold hover:bg-primary/15" aria-label="Um a mais" @click="padBump(1)">+1</button>
            <template v-for="digit in ['7', '8', '9']" :key="digit">
              <button type="button" class="h-12 rounded-md border bg-card text-lg font-semibold tabular-nums hover:bg-accent" :aria-label="`Dígito ${digit}`" @click="padDigit(digit)">{{ digit }}</button>
            </template>
            <button type="button" class="h-12 rounded-md border border-primary/25 bg-primary/8 text-sm font-semibold hover:bg-primary/15" @click="padClear()">Limpar</button>
            <button type="button" class="h-12 rounded-md border bg-card text-lg font-semibold hover:bg-accent" aria-label="Vírgula" @click="padComma()">,</button>
            <button type="button" class="h-12 rounded-md border bg-card text-lg font-semibold tabular-nums hover:bg-accent" aria-label="Dígito 0" @click="padDigit('0')">0</button>
            <button type="button" class="grid h-12 place-items-center rounded-md border bg-card hover:bg-accent" aria-label="Apagar último dígito" @click="padBackspace()">
              <Icon name="lucide:delete" class="size-5" />
            </button>
            <button type="button" class="flex h-12 flex-col items-center justify-center rounded-md border border-primary/25 bg-primary/8 text-sm leading-tight font-semibold hover:bg-primary/15" data-sheet-pad-next @click="padNext()">
              {{ padField === "qty" ? "Valor" : "Qtd." }}
              <Icon name="lucide:arrow-right" class="size-4" />
            </button>
          </div>
        </div>

        <!-- 3b. Chegou diferente da nota: nota × chegou × diferença, e o motivo. -->
        <div data-receipt-field="reason" class="scroll-mt-4 transition-shadow" :class="ring('reason')">
          <ReceiptDifference :preview="preview" @reason="emit('update', { lineNote: $event })" />
        </div>

        <!-- 4. Validade (escolha rápida de dia do kit) e lote, com a leitura da
             embalagem (GS1, C21). -->
        <ReceiptField
          data-receipt-field="expiry"
          class="scroll-mt-4 transition-shadow"
          :class="ring('expiry')"
          :attention="preview.needsExpiry"
          title="Informe a validade"
          icon="lucide:calendar-clock"
        >
          <div class="grid gap-3">
            <div class="grid gap-1 text-xs font-medium text-muted-foreground">
              <span class="flex items-center justify-between gap-2">
                Validade
                <button type="button" class="inline-flex h-9 items-center gap-1.5 rounded-md border border-border bg-card px-2.5 text-xs font-semibold text-foreground hover:bg-accent" data-sheet-read-package @click="emit('read-package')">
                  <Icon name="lucide:scan-text" class="size-4" />
                  Ler da embalagem
                </button>
              </span>
              <OperatorDayPicker v-model="expiryDate" :today="todayIso" label="Validade" />
              <span v-if="preview.line.expiryFromInvoice" class="block text-xs font-normal text-muted-foreground">Veio na nota</span>
              <span v-else-if="preview.needsExpiry" class="block text-xs font-normal text-muted-foreground">A nota não informou. Olhe na embalagem.</span>
            </div>
            <div class="grid gap-3 sm:grid-cols-2">
              <label class="block text-xs font-medium text-muted-foreground">
                Lote do fornecedor
                <input v-model="invoiceLot" class="mt-1 h-11 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground" placeholder="Opcional" />
              </label>
              <label class="block text-xs font-medium text-muted-foreground">
                Ocorrência
                <input v-model="lineNote" class="mt-1 h-11 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground" placeholder="Avaria, falta, ressalva" />
              </label>
            </div>
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

        <div
          v-if="preview.fiscalDivergences.length"
          data-receipt-fiscal-divergences
          class="space-y-1 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning"
        >
          <p v-for="divergence in preview.fiscalDivergences" :key="`${preview.line.id}-${divergence.field}`">
            {{ divergence.message }}
          </p>
          <p class="text-muted-foreground">Nada muda no cadastro ao confirmar: fica como sugestão e aviso para conferir no Admin.</p>
        </div>
      </div>

      <!-- Conferir fecha o item (e a gaveta por cima); a linha lá fora muda de cor. -->
      <footer class="flex shrink-0 flex-col gap-2 border-t border-border bg-card p-4">
        <button
          v-if="!preview.line.checked"
          type="button"
          data-receipt-field="check"
          class="inline-flex h-14 w-full scroll-mt-4 items-center justify-center gap-2.5 rounded-md bg-primary px-3 text-base font-semibold text-primary-foreground transition-shadow"
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
          class="inline-flex h-14 w-full scroll-mt-4 items-center justify-center gap-2.5 rounded-md border border-success/40 bg-success/10 px-3 text-sm font-semibold text-success transition-shadow"
          :class="ring('check')"
          @click="onCheck(false)"
        >
          <Icon name="lucide:circle-check-big" class="size-5 shrink-0" />
          Conferido (toque para desmarcar)
        </button>
        <div class="grid grid-cols-2 gap-2">
          <button
            type="button"
            class="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md border border-border bg-card px-3 text-sm font-medium hover:bg-accent"
            @click="emit('update:open', false)"
          >
            {{ preview.line.checked ? "Fechar" : "Fechar sem conferir" }}
          </button>
          <button
            v-if="hasDifference"
            type="button"
            class="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md px-3 text-sm font-semibold text-destructive hover:bg-destructive/10"
            data-sheet-reject-line
            @click="emit('reject-line')"
          >
            <Icon name="lucide:undo-2" class="size-4" />
            Devolver só este item
          </button>
          <button
            v-else
            type="button"
            class="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md px-3 text-sm font-medium text-destructive hover:bg-destructive/10"
            :aria-label="`Remover ${label}`"
            @click="emit('remove')"
          >
            <Icon name="lucide:trash-2" class="size-4" />
            Remover item da entrada
          </button>
        </div>
      </footer>
    </template>
  </DefineBody>

  <aside
    v-if="docked && preview"
    class="sticky top-36 flex max-h-[calc(100dvh-12rem)] min-w-0 flex-col overflow-hidden rounded-xl border border-border bg-card"
    :data-receipt-sheet="preview.line.id"
    data-receipt-sheet-docked
  >
    <ReuseBody />
  </aside>
  <UiSheet v-else-if="!docked" :open="open" @update:open="emit('update:open', $event)">
    <UiSheetContent
      v-if="preview"
      :data-receipt-sheet="preview.line.id"
      side="right"
      composition="bare"
      class="w-full sm:max-w-xl"
    >
      <ReuseBody />
    </UiSheetContent>
  </UiSheet>
</template>
