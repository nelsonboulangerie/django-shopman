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
import { RECEIPT_LINE_STATUS_COLOR } from "~/utils/receiptLineStatus";
import { FLASH_RING } from "~/utils/receiptFocus";
import { todayIso as todayIsoDate } from "../../../operator-kit/app/presentation/dates";

/**
 * UM item da entrada, aberto por inteiro, e o nome dele SEMPRE à vista.
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
 * O ir e vir entre itens ("Item 3 de 7" e as setas) é da página: ela entrega o
 * `OperatorRecordNav` no slot `nav`, no cabeçalho, nos dois jeitos da gaveta.
 *
 * A lista de itens é um `NuxtSelectMenu` (camada própria do reka): o `Esc` que
 * fecha a lista fecha só a lista, e não a gaveta inteira junto.
 */
const props = defineProps<{
  open: boolean;
  /** `null` enquanto nenhum item está aberto: a gaveta não monta formulário vazio. */
  preview: ReceiptLinePreview | null;
  materials: Material[];
  /** Só as conversões do insumo deste item. */
  conversions: MaterialConversion[];
  pending?: boolean;
  /** Quanto fica no estoque depois desta entrada, na unidade-base do insumo. */
  stockAfter: number;
  /** O campo que a tela acabou de apontar: ganha o anel âmbar por alguns segundos. */
  flashField?: ReceiptFieldAnchor | null;
  /**
   * Tablet (C09): a gaveta encaixada ao lado da lista, sem véu por cima. A lista
   * continua tocável e o item vizinho abre sem fechar a gaveta (slot `nav`).
   */
  docked?: boolean;
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
  "scan-ean": [];
  "read-package": [];
  "reject-line": [];
}>();

defineSlots<{
  /** O ir e vir entre itens (a página passa o `OperatorRecordNav`). */
  nav?: () => unknown;
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
function padFocus(field: PadField) {
  padField.value = field;
  padFresh.value = true;
}
const hasDifference = computed(() => (props.preview ? Boolean(receiptLineDifference(props.preview.line)) : false));

// O insumo vira item do `NuxtSelectMenu`: o SKU e a unidade seguem pesquisáveis (é
// o que o operador lê na etiqueta quando o nome não bate), e a categoria entra só
// na busca, porque na linha ela não caberia.
const materialItems = computed(() =>
  props.materials.map((material) => ({
    value: material.sku,
    label: material.name,
    description: `${material.sku} · conta em ${material.unit}`,
    keywords: material.category,
  })),
);
// O nome escolhido pode passar da largura do campo: a reticência leva o completo na
// dica (o rótulo que cabe, dono 10/10/2026).
const materialName = computed(
  () => props.materials.find((material) => material.sku === props.preview?.line.materialSku)?.name || undefined,
);
// No toque, a busca não pega o foco ao abrir: o teclado virtual só sobe quando a
// pessoa toca na busca.
const touch = useCoarsePointer();
const materialSearch = computed(() => ({ placeholder: "Buscar item do Compras", autofocus: !touch.value }));

const label = computed(() => (props.preview ? receiptLineLabel(props.preview) : ""));
const status = computed(() => (props.preview ? receiptLineStatus(props.preview) : "ready"));
const badge = computed(() => receiptLineStatusBadge(status.value));
const invoiceSummary = computed(() => props.preview?.invoiceSummary || "Lançado à mão, sem documento fiscal.");

/**
 * Os campos de digitar continuam com `v-model`, e não com `:value`/`@input`.
 *
 * Não é preguiça: a diretiva do `v-model` sabe não sobrescrever o que está
 * sendo digitado (`1,` a caminho de `1,5`), e uma ligação de atributo à mão
 * apaga o dígito no meio da digitação. O `set` de cada um manda o patch para
 * quem é dono da linha: mutar a prop aqui dentro seria escrever no rascunho
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

const warningColor: Record<ReceiptWarningTone, "success" | "warning" | "error"> = {
  ok: "success",
  watch: "warning",
  block: "error",
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
      <header class="shrink-0 space-y-2 border-b border-border bg-card p-3" data-slot="sheet-header">
        <div class="flex items-start justify-between gap-2">
          <NuxtBadge :color="RECEIPT_LINE_STATUS_COLOR[status]" :icon="badge.icon" :label="badge.label" data-receipt-sheet-status />
          <!-- O ir e vir é da página (slot `nav`). Por cima, Fechar fica ao lado dele,
               nunca a lixeira. -->
          <div class="flex items-center gap-1.5">
            <slot name="nav" />
            <NuxtButton
              v-if="!docked"
              variant="ghost"
              color="neutral"
              square
              icon="i-lucide-x"
              aria-label="Fechar"
              data-receipt-sheet-close
              @click="emit('update:open', false)"
            />
          </div>
        </div>
        <h2 class="text-base font-semibold" data-slot="sheet-title">{{ label }}</h2>
        <p class="text-sm text-muted-foreground" data-slot="sheet-description">{{ invoiceSummary }}</p>
        <NuxtAlert
          v-if="preview.nextStep"
          variant="subtle"
          color="warning"
          icon="i-lucide-arrow-right"
          :title="preview.nextStep"
          data-receipt-sheet-next-step
        />
      </header>

      <!-- O corpo rola por baixo do cabeçalho. -->
      <div class="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        <div v-if="preview.line.invoiceTotal" class="flex items-center justify-between gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm">
          <span class="text-xs font-medium text-muted-foreground">Valor na nota</span>
          <span class="font-semibold tabular-nums">{{ preview.line.invoiceTotal }}</span>
        </div>

        <!-- 1. Qual insumo é, com o EAN pela câmera ao lado (C11). -->
        <ReceiptField
          data-receipt-field="material"
          class="scroll-mt-4 transition-shadow"
          :class="ring('material')"
          :attention="Boolean(preview.suggestion) || (!preview.line.materialSku && !preview.suggestion)"
          :title="preview.suggestion ? 'Confirme a sugestão' : 'Escolha o item desta linha'"
          :icon="preview.suggestion ? 'lucide:sparkles' : 'lucide:package-search'"
        >
          <NuxtFormField label="Item">
            <div class="flex gap-2">
              <NuxtSelectMenu
                class="min-w-0 flex-1"
                :items="materialItems"
                value-key="value"
                :filter-fields="['label', 'description', 'keywords']"
                :model-value="preview.line.materialSku || undefined"
                :title="materialName"
                :search-input="materialSearch"
                placeholder="Escolher item"
                data-receipt-material-select
                @update:model-value="(sku: unknown) => sku && emit('selectMaterial', String(sku))"
              >
                <template #empty>Nenhum item do Compras com esse nome.</template>
              </NuxtSelectMenu>
              <NuxtButton
                variant="outline"
                color="neutral"
                icon="i-lucide-scan-barcode"
                label="EAN"
                aria-label="Ler o EAN do item pela câmera"
                data-sheet-scan-ean
                @click="emit('scan-ean')"
              />
            </div>
          </NuxtFormField>
          <p v-if="preview.line.scannedEan" class="mt-1 text-xs text-muted-foreground tnum">EAN lido: {{ preview.line.scannedEan }}</p>
          <template v-if="preview.suggestion">
            <p v-if="preview.suggestion.byBarcode" class="mt-2 text-xs text-muted-foreground">
              O código de barras da nota é o de <span class="font-medium text-foreground">{{ preview.suggestion.name }}</span>
            </p>
            <p v-else class="mt-2 text-xs text-muted-foreground">
              Parece <span class="font-medium text-foreground">{{ preview.suggestion.name }}</span> ({{ preview.suggestion.scorePercent }}% parecido)
            </p>
            <NuxtButton class="mt-2 justify-center" icon="i-lucide-check" label="É este" @click="emit('acceptSuggestion')" />
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
             fica marcado; tocar no outro campo troca o alvo do teclado. -->
        <div data-receipt-field="qty" class="scroll-mt-4 space-y-2 transition-shadow" :class="ring('qty')">
          <div class="grid gap-2 sm:grid-cols-2">
            <NuxtButton
              size="xl"
              variant="outline"
              color="neutral"
              :active="padField === 'qty'"
              active-variant="outline"
              active-color="primary"
              block
              class="min-h-16 flex-col items-start justify-center text-left"
              :aria-pressed="padField === 'qty'"
              data-sheet-qty-field
              @click="padFocus('qty')"
            >
              <span class="text-xs font-medium text-muted-foreground">Quantidade{{ preview.purchaseUnitLabel ? ` (${preview.purchaseUnitLabel})` : "" }}</span>
              <span class="flex w-full items-baseline justify-between gap-2">
                <span class="text-2xl font-semibold tabular-nums">{{ String(preview.line.purchaseQty ?? 0).replace(".", ",") }}</span>
                <span v-if="preview.baseQtyKnown && preview.line.materialSku" class="text-xs font-normal text-muted-foreground tabular-nums">
                  entra {{ formatQty(preview.baseQty, preview.material.unit) }}
                </span>
              </span>
            </NuxtButton>
            <NuxtButton
              size="xl"
              variant="outline"
              color="neutral"
              :active="padField === 'cost'"
              active-variant="outline"
              active-color="primary"
              block
              class="min-h-16 flex-col items-start justify-center text-left"
              :aria-pressed="padField === 'cost'"
              data-sheet-cost-field
              @click="padFocus('cost')"
            >
              <span class="text-xs font-medium text-muted-foreground">Valor total (R$)</span>
              <span class="flex w-full items-baseline justify-between gap-2">
                <span class="text-2xl font-semibold tabular-nums">{{ preview.line.costInput || "0,00" }}</span>
                <span v-if="preview.baseQtyKnown && preview.baseCostQ > 0" class="text-xs font-normal text-muted-foreground tabular-nums">
                  {{ formatMoney(preview.baseCostQ) }}/{{ preview.material.unit }}
                </span>
              </span>
            </NuxtButton>
          </div>
          <div class="grid grid-cols-4 gap-1.5" role="group" aria-label="Teclado numérico do item" data-sheet-numpad>
            <template v-for="digit in ['1', '2', '3']" :key="digit">
              <NuxtButton size="xl" variant="outline" color="neutral" block class="justify-center tabular-nums" :label="digit" :aria-label="`Dígito ${digit}`" @click="padDigit(digit)" />
            </template>
            <NuxtButton size="xl" variant="outline" block class="justify-center" label="−1" aria-label="Um a menos" @click="padBump(-1)" />
            <template v-for="digit in ['4', '5', '6']" :key="digit">
              <NuxtButton size="xl" variant="outline" color="neutral" block class="justify-center tabular-nums" :label="digit" :aria-label="`Dígito ${digit}`" @click="padDigit(digit)" />
            </template>
            <NuxtButton size="xl" variant="outline" block class="justify-center" label="+1" aria-label="Um a mais" @click="padBump(1)" />
            <template v-for="digit in ['7', '8', '9']" :key="digit">
              <NuxtButton size="xl" variant="outline" color="neutral" block class="justify-center tabular-nums" :label="digit" :aria-label="`Dígito ${digit}`" @click="padDigit(digit)" />
            </template>
            <NuxtButton size="xl" variant="outline" block class="justify-center" label="Limpar" @click="padClear()" />
            <NuxtButton size="xl" variant="outline" color="neutral" block class="justify-center" label="," aria-label="Vírgula" @click="padComma()" />
            <NuxtButton size="xl" variant="outline" color="neutral" block class="justify-center tabular-nums" label="0" aria-label="Dígito 0" @click="padDigit('0')" />
            <NuxtButton
              size="xl"
              variant="outline"
              color="neutral"
              block
              square
              class="justify-center"
              icon="i-lucide-delete"
              aria-label="Apagar último dígito"
              @click="padBackspace()"
            />
            <NuxtButton
              size="xl"
              variant="outline"
              block
              class="justify-center"
              trailing-icon="i-lucide-arrow-right"
              :label="padField === 'qty' ? 'Valor' : 'Qtd.'"
              :aria-label="padField === 'qty' ? 'Ir para o valor total' : 'Ir para a quantidade'"
              data-sheet-pad-next
              @click="padNext()"
            />
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
            <div class="grid gap-1">
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs font-medium text-muted-foreground">Validade</span>
                <NuxtButton
                  variant="outline"
                  color="neutral"
                  icon="i-lucide-scan-text"
                  label="Ler da embalagem"
                  data-sheet-read-package
                  @click="emit('read-package')"
                />
              </div>
              <OperatorDayPicker v-model="expiryDate" :today="todayIso" label="Validade" />
              <span v-if="preview.line.expiryFromInvoice" class="block text-xs text-muted-foreground">Veio na nota</span>
              <span v-else-if="preview.needsExpiry" class="block text-xs text-muted-foreground">A nota não informou. Olhe na embalagem.</span>
            </div>
            <div class="grid gap-3 sm:grid-cols-2">
              <NuxtFormField label="Lote do fornecedor">
                <NuxtInput v-model="invoiceLot" class="w-full" placeholder="Opcional" data-receipt-lot />
              </NuxtFormField>
              <NuxtFormField label="Ocorrência">
                <NuxtInput v-model="lineNote" class="w-full" placeholder="Avaria, falta, ressalva" data-receipt-note />
              </NuxtFormField>
            </div>
          </div>
        </ReceiptField>

        <!-- 5. O que entra no estoque, e a consequência disso. -->
        <div class="rounded-md border border-border bg-card px-3 py-2">
          <template v-if="preview.baseQtyKnown && preview.line.materialSku">
            <p class="text-base font-semibold tabular-nums">Entra {{ formatQty(preview.baseQty, preview.material.unit) }}</p>
            <p class="mt-0.5 text-xs text-muted-foreground">
              Estoque depois: {{ formatQty(stockAfter, preview.material.unit) }}
            </p>
          </template>
          <p v-else class="text-sm text-muted-foreground">A entrada aparece aqui quando o insumo e a embalagem estiverem definidos.</p>
        </div>

        <div v-if="visibleWarnings.length" class="flex flex-wrap gap-1.5">
          <NuxtBadge
            v-for="warning in visibleWarnings"
            :key="`${preview.line.id}-${warning.key}`"
            :color="warningColor[warning.tone]"
            :label="warning.label"
          />
        </div>

        <NuxtAlert
          v-if="preview.fiscalDivergences.length"
          variant="subtle"
          color="warning"
          icon="i-lucide-triangle-alert"
          data-receipt-fiscal-divergences
        >
          <template #description>
            <p v-for="divergence in preview.fiscalDivergences" :key="`${preview.line.id}-${divergence.field}`">
              {{ divergence.message }}
            </p>
            <p class="mt-1">Nada muda no cadastro ao confirmar: fica como sugestão e aviso para conferir no Admin.</p>
          </template>
        </NuxtAlert>
      </div>

      <!-- Conferir fecha o item (e a gaveta por cima); a linha lá fora muda de cor. -->
      <footer class="flex shrink-0 flex-col gap-2 border-t border-border bg-card p-3">
        <NuxtButton
          size="xl"
          block
          :active="preview.line.checked"
          active-variant="outline"
          active-color="neutral"
          icon="i-lucide-circle-check-big"
          class="scroll-mt-4 justify-center transition-shadow"
          :class="ring('check')"
          :label="preview.line.checked ? 'Conferido (toque para desmarcar)' : 'Marcar como conferido'"
          data-receipt-field="check"
          @click="onCheck(!preview.line.checked)"
        />
        <div class="grid grid-cols-2 gap-2">
          <NuxtButton
            variant="outline"
            color="neutral"
            block
            class="justify-center"
            :label="preview.line.checked ? 'Fechar' : 'Fechar sem conferir'"
            @click="emit('update:open', false)"
          />
          <NuxtButton
            v-if="hasDifference"
            variant="ghost"
            color="error"
            block
            class="justify-center"
            icon="i-lucide-undo-2"
            label="Devolver só este item"
            data-sheet-reject-line
            @click="emit('reject-line')"
          />
          <NuxtButton
            v-else
            variant="ghost"
            color="error"
            block
            class="justify-center"
            icon="i-lucide-trash-2"
            label="Remover item da entrada"
            :aria-label="`Remover ${label}`"
            @click="emit('remove')"
          />
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
  <!-- Por cima: o título e a descrição do diálogo (leitor de tela) são os mesmos que
       o cabeçalho mostra. -->
  <NuxtSlideover
    v-else-if="!docked"
    :open="open && Boolean(preview)"
    side="right"
    :title="label || 'Item da entrada'"
    :description="invoiceSummary"
    class="w-full max-w-none sm:max-w-xl"
    @update:open="emit('update:open', $event)"
  >
    <template #content>
      <div v-if="preview" class="flex h-full min-h-0 flex-col" :data-receipt-sheet="preview.line.id">
        <ReuseBody />
      </div>
    </template>
  </NuxtSlideover>
</template>
