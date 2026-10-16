<script setup lang="ts">
import type { Material, ReceiptExceptionView, ReceiptLinePreview } from "~/types/purchase";
import {
  formatMoney,
  formatShortDate,
  receiptExpiryShortcuts,
  receiptLineDifference,
  receiptLineLabel,
  receiptSettledSummary,
} from "~/presentation/purchase";
import { todayIso as todayIsoDate } from "../../../operator-kit/app/presentation/dates";

/**
 * A conferência por exceção da entrada com NF (Compras › Receber, na doca).
 *
 * Decisão do dono (03/10/2026): "recebimento por exceção, sim; validade é
 * incontornável". O desenho é o da prévia v4 (`compras-validade4.html`):
 *
 * a. **Tudo bate com a nota**: o que o sistema já sabe, em três fatos com a marca
 *    de automático (de-para, embalagens, preços), e os itens recolhidos em "Ver
 *    os N itens". **Contei os volumes** é o único ato físico; o "Contei N
 *    volumes" mora no polegar (no celular, a barra da página) com "Algo não
 *    bate" logo abaixo. "Bipar cada volume" conta pela câmera.
 * b. **Falta só a validade**: com os volumes contados, o cartão dos volumes
 *    recolhe numa linha e a validade vira o foco no topo, uma linha perecível por
 *    vez: "Mesma da última entrega", a típica, "Ler da embalagem" e "Outra data".
 * c. **Um item não bate**: só ele se resolve, aberto no próprio fluxo (nota ×
 *    chegou × diferença, contados, motivo, consequência), com os que batem num
 *    cartão recolhido e "Devolver só este item".
 */
const props = defineProps<{
  view: ReceiptExceptionView;
  materials: Material[];
  lineCount: number;
  totalCostQ: number;
  declaredVolumes: number;
  pending?: boolean;
  /** O anel âmbar de quando o "Confirmar entrada" aponta para a contagem. */
  volumesRing?: string;
  /** O "Contei N volumes" mora fora do cartão (no polegar do celular). */
  countInThumb?: boolean;
  /** Esconde o que já bate (o "Ver os N itens" fechado): "Algo não bate" abre. */
  matchedOpen?: boolean;
}>();

const emit = defineEmits<{
  count: [counted: number | null];
  expiry: [lineId: string, date: string];
  open: [lineId: string];
  "scan-volumes": [];
  "read-package": [lineId: string];
  qty: [lineId: string, qty: number];
  reason: [lineId: string, reason: string];
  "reject-line": [lineId: string];
  "update:matchedOpen": [open: boolean];
}>();

const todayIso = todayIsoDate();

// O stepper nasce no número esperado: contar e bater é o caso comum, e o
// recebedor só mexe quando a doca diz outra coisa. O rascunho é do pai (o
// "Contei N volumes" do polegar lê o mesmo número).
const draftCount = defineModel<number>("draft", { default: 0 });
watch(
  () => [props.view.expectedVolumes, props.view.countedVolumes] as const,
  ([expected, counted]) => {
    if (counted !== null) draftCount.value = counted;
    else if (expected !== null && !draftCount.value) draftCount.value = expected;
  },
  { immediate: true },
);

function stepCount(delta: number) {
  draftCount.value = Math.max(0, draftCount.value + delta);
  // Mexeu no número depois de declarar: a declaração deixa de valer até o
  // próximo "Contei".
  if (props.view.countedVolumes !== null) emit("count", null);
}

const countDeclared = computed(() => props.view.countedVolumes !== null && props.view.countedVolumes === draftCount.value);
const countMatches = computed(() => draftCount.value === props.view.expectedVolumes);
const countMismatch = computed(() => props.view.countedVolumes !== null && !props.view.countOk);
// Contou e bateu: o cartão dos volumes recolhe e a validade sobe para o topo (v4 b).
const volumesSettled = computed(() => props.view.countOk && props.view.countedVolumes !== null);

const volumesSource = computed(() =>
  props.declaredVolumes > 0 ? `A nota diz ${props.view.expectedVolumes} volumes (caixas, sacos, fardos)`
  : `As embalagens da nota somam ${props.view.expectedVolumes} volumes`,
);

const headline = computed(() =>
  props.view.exceptions.length === 0 ? "Tudo bate com a nota"
  : `${props.view.matched.length} ${props.view.matched.length === 1 ? "bate" : "batem"} · ${props.view.exceptions.length} para resolver`,
);

// Os três fatos que o sistema conferiu sozinho (v4 a, pino 1).
const autoFacts = [
  "Itens reconhecidos pelo de-para",
  "Embalagens conferem com o cadastro",
  "Preços dentro do último pago",
];

const pendingExpiries = computed(() => props.view.perishables.filter((preview) => !preview.line.expiryDate).length);
// Os itens que não pedem validade: entram "ok" de cara (v4 b, última linha).
const noExpiryItems = computed(() => {
  const perishable = new Set(props.view.perishables.map((preview) => preview.line.id));
  return props.view.matched.filter((preview) => !perishable.has(preview.line.id));
});
const noExpirySummary = computed(() => noExpiryItems.value.map((preview) => receiptLineLabel(preview)).join(", "));

// ── Validade, uma linha por vez ─────────────────────────────────────────────
// "Trocar" traz de volta uma validade já dada; sem troca, a vez é do próximo
// perecível sem data.
const expiryFocusId = ref<string | null>(null);
const otherDateOpen = ref(false);
const currentExpiry = computed<ReceiptLinePreview | null>(() => {
  if (expiryFocusId.value) {
    const focused = props.view.perishables.find((preview) => preview.line.id === expiryFocusId.value);
    if (focused) return focused;
  }
  return props.view.nextExpiry;
});
const expiryDoneList = computed(() =>
  props.view.perishables.filter((preview) => preview.line.expiryDate && preview.line.id !== currentExpiry.value?.line.id),
);
const currentShortcuts = computed(() => {
  const preview = currentExpiry.value;
  if (!preview) return [];
  const material = props.materials.find((item) => item.sku === preview.line.materialSku) ?? preview.material;
  return receiptExpiryShortcuts(material, todayIso);
});
const otherDate = ref("");
watch(currentExpiry, () => {
  otherDateOpen.value = false;
  otherDate.value = "";
});
watch(otherDate, (date) => {
  if (date && currentExpiry.value) chooseExpiry(currentExpiry.value.line.id, date);
});

function chooseExpiry(lineId: string, date: string) {
  emit("expiry", lineId, date);
  expiryFocusId.value = null;
}

function swapExpiry(lineId: string) {
  expiryFocusId.value = lineId;
}

// ── O item que não bate (v4 c) ──────────────────────────────────────────────
const currentException = computed(() => props.view.exceptions.find((preview) => preview.nextStep) ?? props.view.exceptions[0] ?? null);
const exceptionUnit = computed(() =>
  currentException.value ? currentException.value.purchaseUnitLabel || currentException.value.material.unit : "",
);
function exceptionDigest(preview: ReceiptLinePreview): string {
  const difference = receiptLineDifference(preview.line);
  if (difference) {
    const unit = preview.purchaseUnitLabel || preview.material.unit;
    return `Nota ${difference.invoiceQty} · chegou ${difference.arrivedQty} ${unit}`;
  }
  return preview.nextStep || (preview.line.checked ? "Conferido" : "Conferir e marcar como conferido");
}
function bumpException(delta: number) {
  const preview = currentException.value;
  if (!preview) return;
  emit("qty", preview.line.id, Math.max(0, (preview.line.purchaseQty || 0) + delta));
}

const matchedExpanded = computed({
  get: () => Boolean(props.matchedOpen),
  set: (open: boolean) => emit("update:matchedOpen", open),
});
const matchedNames = computed(() => props.view.matched.map((preview) => receiptLineLabel(preview)).join(", "));
</script>

<template>
  <section class="space-y-3" aria-label="Conferência por exceção" data-exception-flow>
    <!-- c. Um item não bate: progresso e o item, no topo. -->
    <template v-if="view.exceptions.length">
      <NuxtCard data-exception-progress>
        <div class="flex items-baseline justify-between gap-2">
          <h2 class="text-base font-semibold">{{ headline }}</h2>
          <span v-if="view.perishables.length" class="text-xs text-muted-foreground tnum">validade {{ view.expiryDone }} de {{ view.perishables.length }}</span>
        </div>
        <div class="mt-2 flex h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
          <span class="h-full bg-success" :style="{ width: `${(view.matched.length / Math.max(1, lineCount)) * 100}%` }" />
          <span class="h-full bg-warning" :style="{ width: `${(view.exceptions.length / Math.max(1, lineCount)) * 100}%` }" />
        </div>
      </NuxtCard>

      <NuxtCard v-if="currentException" class="ring-2 ring-warning" :data-exception-item="currentException.line.id">
        <div class="flex items-start gap-2.5">
          <Icon name="lucide:triangle-alert" class="mt-0.5 size-5 shrink-0 text-warning" />
          <div class="min-w-0 flex-1">
            <h3 class="text-base font-semibold" :title="receiptLineLabel(currentException)">{{ receiptLineLabel(currentException) }}</h3>
            <p class="text-sm text-muted-foreground tnum">{{ exceptionDigest(currentException) }}</p>
          </div>
          <NuxtButton variant="ghost" label="Detalhes" @click="emit('open', currentException.line.id)" />
        </div>
        <ReceiptDifference class="mt-3" :preview="currentException" @reason="emit('reason', currentException.line.id, $event)" />
        <div v-if="receiptLineDifference(currentException.line)" class="mt-3 flex items-center gap-3">
          <NuxtButton
            size="xl"
            variant="outline"
            color="neutral"
            square
            icon="i-lucide-minus"
            aria-label="Um a menos"
            :disabled="pending"
            @click="bumpException(-1)"
          />
          <p class="min-w-0 flex-1 text-center text-base font-semibold tnum">{{ currentException.line.purchaseQty }} {{ exceptionUnit }} contados</p>
          <NuxtButton
            size="xl"
            variant="outline"
            color="neutral"
            square
            icon="i-lucide-plus"
            aria-label="Um a mais"
            :disabled="pending"
            @click="bumpException(1)"
          />
        </div>
        <ul v-if="view.exceptions.length > 1" class="mt-3 grid grid-cols-1 gap-2">
          <li v-for="preview in view.exceptions.filter((item) => item.line.id !== currentException?.line.id)" :key="`exception-${preview.line.id}`">
            <NuxtButton
              size="xl"
              variant="outline"
              color="neutral"
              block
              class="justify-start text-left"
              @click="emit('open', preview.line.id)"
            >
              <Icon name="lucide:triangle-alert" class="size-5 shrink-0 text-warning" />
              <span class="min-w-0 flex-1 text-sm font-semibold" :title="receiptLineLabel(preview)">{{ receiptLineLabel(preview) }}</span>
              <span class="shrink-0 text-xs font-normal text-muted-foreground tnum">{{ exceptionDigest(preview) }}</span>
            </NuxtButton>
          </li>
        </ul>
      </NuxtCard>
    </template>

    <!-- a. O que o sistema já sabe (some quando há exceção: vira o cartão recolhido abaixo). -->
    <NuxtCard v-if="!view.exceptions.length && !volumesSettled" data-exception-verdict>
      <div class="flex items-start gap-3">
        <span class="grid size-10 shrink-0 place-items-center rounded-full bg-success text-white">
          <Icon name="lucide:check-check" class="size-5" />
        </span>
        <div class="min-w-0 flex-1">
          <h2 class="text-base font-semibold">{{ headline }}</h2>
          <p class="mt-0.5 text-sm tnum">
            {{ lineCount }} {{ lineCount === 1 ? "item" : "itens" }}<template v-if="totalCostQ > 0"> · {{ formatMoney(totalCostQ) }}</template>
          </p>
        </div>
      </div>
      <ul class="mt-3 grid gap-1.5" data-exception-facts>
        <li v-for="fact in autoFacts" :key="fact" class="flex items-center gap-2 text-sm">
          <Icon name="lucide:sparkles" class="size-4 shrink-0 text-muted-foreground" />
          {{ fact }}
        </li>
      </ul>
      <NuxtButton
        class="mt-3"
        variant="ghost"
        :trailing-icon="matchedExpanded ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
        :label="`Ver os ${lineCount} itens`"
        :aria-expanded="matchedExpanded"
        data-exception-see-items
        @click="matchedExpanded = !matchedExpanded"
      />
      <ul v-if="matchedExpanded" class="mt-1 grid grid-cols-1 gap-2">
        <li v-for="preview in view.matched" :key="`matched-${preview.line.id}`">
          <NuxtButton
            size="xl"
            variant="outline"
            color="neutral"
            block
            trailing-icon="i-lucide-chevron-right"
            class="justify-start text-left"
            @click="emit('open', preview.line.id)"
          >
            <span class="min-w-0 flex-1 text-sm font-semibold" :title="receiptLineLabel(preview)">{{ receiptLineLabel(preview) }}</span>
            <span class="shrink-0 text-xs font-normal text-muted-foreground tnum">{{ receiptSettledSummary(preview) }}</span>
          </NuxtButton>
        </li>
      </ul>
    </NuxtCard>

    <!-- b. A validade é incontornável: com os volumes contados, ela é o foco no topo. -->
    <div v-if="view.perishables.length && (volumesSettled || view.exceptions.length)" class="space-y-2" data-exception-expiry>
      <div class="flex items-baseline justify-between gap-2 px-0.5">
        <h3 class="text-base font-semibold">{{ view.nextExpiry ? "Falta só a validade" : "Validades" }}</h3>
        <span class="text-sm font-semibold tnum">{{ view.expiryDone }} de {{ view.perishables.length }}</span>
      </div>
      <div class="flex gap-1.5" aria-hidden="true">
        <span
          v-for="preview in view.perishables"
          :key="`bar-${preview.line.id}`"
          class="h-2 flex-1 rounded-full"
          :class="preview.line.expiryDate ? 'bg-success' : 'bg-primary/25'"
        />
      </div>

      <NuxtCard v-if="currentExpiry" class="ring-2 ring-primary" :data-receipt-expiry="currentExpiry.line.id">
        <div class="flex items-center gap-2.5">
          <span class="grid size-9 shrink-0 place-items-center rounded-full bg-primary/12 text-primary">
            <Icon name="lucide:calendar-clock" class="size-5" />
          </span>
          <div class="min-w-0 flex-1">
            <p class="text-base font-semibold" :title="receiptLineLabel(currentExpiry)">{{ receiptLineLabel(currentExpiry) }}</p>
            <p class="text-sm text-muted-foreground tnum">{{ receiptSettledSummary(currentExpiry) }} · vence quando?</p>
          </div>
        </div>
        <div class="mt-3 grid grid-cols-2 gap-2">
          <NuxtButton
            v-for="(shortcut, index) in currentShortcuts"
            :key="shortcut.key"
            size="xl"
            variant="outline"
            color="neutral"
            :active="index === 0"
            active-variant="outline"
            active-color="primary"
            block
            :icon="shortcut.key === 'last' ? 'i-lucide-history' : 'i-lucide-calendar-plus'"
            class="col-span-2 justify-start text-left"
            :disabled="pending"
            :data-expiry-shortcut="shortcut.key"
            @click="chooseExpiry(currentExpiry.line.id, shortcut.date)"
          >
            <span class="flex-1 text-sm font-semibold">{{ shortcut.label }}</span>
            <span class="text-xs font-normal text-muted-foreground tnum">{{ shortcut.caption }}</span>
          </NuxtButton>
          <NuxtButton
            size="xl"
            variant="outline"
            color="neutral"
            block
            icon="i-lucide-scan-text"
            class="justify-start text-left"
            :disabled="pending"
            data-expiry-read-package
            @click="emit('read-package', currentExpiry.line.id)"
          >
            <!-- Rótulo no slot: o do Nuxt UI corta ("Ler da emba…") a 390 px. -->
            <span class="text-sm font-medium">Ler da embalagem</span>
          </NuxtButton>
          <!-- O rótulo que cabe (dono, 10/10/2026): a 320 px a meia coluna não cabe
               "Outra data" ao lado do calendário; vira só o ícone, com o nome na dica. -->
          <div v-if="!otherDateOpen" class="op-fit-scope">
            <OperatorButton
              size="xl"
              variant="outline"
              color="neutral"
              block
              icon="i-lucide-calendar"
              label="Outra data"
              class="justify-start"
              @click="otherDateOpen = true"
            />
          </div>
          <OperatorDayPicker v-else v-model="otherDate" class="col-span-2" :today="todayIso" label="Validade" />
        </div>
        <p class="mt-2 text-sm text-muted-foreground">Um toque grava e passa para o próximo.</p>
      </NuxtCard>

      <ul v-if="expiryDoneList.length || noExpiryItems.length" class="grid grid-cols-1 gap-2">
        <li
          v-for="preview in expiryDoneList"
          :key="`expiry-${preview.line.id}`"
          class="flex min-h-12 items-center gap-3 rounded-md border border-success/30 bg-success/5 px-3 py-1.5"
        >
          <Icon name="lucide:circle-check-big" class="size-5 shrink-0 text-success" />
          <span class="min-w-0 flex-1">
            <span class="block text-sm font-semibold" :title="receiptLineLabel(preview)">{{ receiptLineLabel(preview) }}</span>
            <span class="block text-xs text-muted-foreground tnum">
              Vence {{ formatShortDate(preview.line.expiryDate) }}<template v-if="preview.line.expiryFromInvoice"> · veio na nota</template><template v-else-if="preview.line.invoiceLot"> · lote {{ preview.line.invoiceLot }}</template>
            </span>
          </span>
          <NuxtButton variant="ghost" label="Trocar" @click="swapExpiry(preview.line.id)" />
        </li>
        <li
          v-if="noExpiryItems.length"
          class="flex min-h-12 items-center gap-3 rounded-md border border-border bg-card px-3 py-1.5"
          data-expiry-none
        >
          <Icon name="lucide:check" class="size-5 shrink-0 text-muted-foreground" />
          <span class="min-w-0 flex-1 text-sm" :title="noExpirySummary">
            <b class="font-semibold">{{ noExpiryItems.length }} sem validade</b>
            <span class="text-muted-foreground"> {{ noExpirySummary }}</span>
          </span>
          <NuxtBadge color="success" label="ok" />
        </li>
      </ul>
    </div>

    <!-- Contei os volumes: o único ato físico. Contado e batendo, recolhe numa linha. -->
    <div
      v-if="view.available && volumesSettled"
      class="flex min-h-12 items-center gap-3 rounded-md border border-success/30 bg-success/5 px-3"
      data-volumes-settled
    >
      <Icon name="lucide:package-check" class="size-5 shrink-0 text-success" />
      <span class="min-w-0 flex-1 text-sm">
        <b class="tnum">{{ view.countedVolumes }} de {{ view.expectedVolumes }}</b> volumes contados
      </span>
      <NuxtButton variant="ghost" label="Recontar" @click="emit('count', null)" />
    </div>
    <NuxtCard
      v-else-if="view.available"
      data-receipt-anchor="volumes"
      class="scroll-mt-4 transition-shadow"
      :class="[countMismatch ? 'ring-2 ring-destructive' : 'ring-2 ring-primary', volumesRing]"
    >
      <p class="text-xs font-semibold" :class="countMismatch ? 'text-destructive' : 'text-primary'">O que só você vê</p>
      <h3 class="mt-1 text-base font-semibold">Contei os volumes</h3>
      <p class="text-sm text-muted-foreground">{{ volumesSource }}</p>

      <div class="mt-3 flex items-center gap-3">
        <NuxtButton
          size="xl"
          variant="outline"
          color="neutral"
          square
          icon="i-lucide-minus"
          aria-label="Um volume a menos"
          :disabled="pending || draftCount <= 0"
          @click="stepCount(-1)"
        />
        <div
          class="flex h-14 min-w-0 flex-1 items-center justify-center gap-1.5 rounded-md border tnum"
          :class="countMatches ? 'border-success/40 bg-success/8' : 'border-warning/40 bg-warning/8'"
          aria-live="polite"
        >
          <span class="text-2xl leading-none font-semibold">{{ draftCount }}</span>
          <span class="text-base font-medium text-muted-foreground">de {{ view.expectedVolumes }}</span>
          <Icon v-if="countMatches" name="lucide:circle-check" class="ml-1 size-5 text-success" />
        </div>
        <NuxtButton
          size="xl"
          variant="outline"
          color="neutral"
          square
          icon="i-lucide-plus"
          aria-label="Um volume a mais"
          :disabled="pending"
          @click="stepCount(1)"
        />
      </div>

      <NuxtButton
        class="mt-3 justify-center"
        size="xl"
        variant="outline"
        color="neutral"
        block
        icon="i-lucide-scan-barcode"
        label="Bipar cada volume"
        :disabled="pending"
        data-scan-volumes
        @click="emit('scan-volumes')"
      />

      <NuxtButton
        v-if="!countDeclared && !countInThumb"
        class="mt-2 justify-center"
        size="xl"
        block
        icon="i-lucide-check"
        :label="`Contei ${draftCount} ${draftCount === 1 ? 'volume' : 'volumes'}`"
        :disabled="pending || draftCount <= 0"
        @click="emit('count', draftCount)"
      />
      <NuxtAlert
        v-if="countMismatch"
        class="mt-3"
        variant="subtle"
        color="error"
        icon="i-lucide-circle-alert"
        :title="`Contou ${view.countedVolumes} de ${view.expectedVolumes}.`"
        description="Abra o item que chegou diferente e corrija a quantidade que chegou."
      />

      <!-- Contagem que não fecha: a lista do que bate vira a lista de onde procurar. -->
      <ul v-if="countMismatch && view.matched.length" class="mt-3 grid grid-cols-1 gap-2">
        <li v-for="preview in view.matched" :key="`count-${preview.line.id}`">
          <NuxtButton
            size="xl"
            variant="outline"
            color="neutral"
            block
            trailing-icon="i-lucide-chevron-right"
            class="justify-start text-left"
            @click="emit('open', preview.line.id)"
          >
            <span class="min-w-0 flex-1 text-sm font-semibold" :title="receiptLineLabel(preview)">{{ receiptLineLabel(preview) }}</span>
            <span class="shrink-0 text-xs font-normal text-muted-foreground tnum">{{ receiptSettledSummary(preview) }}</span>
          </NuxtButton>
        </li>
      </ul>
    </NuxtCard>
    <p
      v-if="view.available && !volumesSettled && pendingExpiries > 0"
      class="flex items-center gap-2 px-1 text-sm text-muted-foreground"
      data-volumes-next
    >
      <Icon name="lucide:calendar-clock" class="size-4 shrink-0" />
      Depois: só a validade de {{ pendingExpiries }} {{ pendingExpiries === 1 ? "perecível" : "perecíveis" }}
    </p>

    <!-- c. O que bate, recolhido num cartão (só quando há exceção). -->
    <NuxtCard v-if="view.exceptions.length && view.matched.length" data-exception-matched>
      <NuxtButton
        variant="ghost"
        color="neutral"
        block
        class="justify-start text-left"
        :trailing-icon="matchedExpanded ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
        :aria-expanded="matchedExpanded"
        @click="matchedExpanded = !matchedExpanded"
      >
        <Icon name="lucide:circle-check-big" class="size-5 shrink-0 text-success" />
        <span class="min-w-0 flex-1">
          <span class="block text-base font-semibold">{{ view.matched.length }} {{ view.matched.length === 1 ? "item bate" : "itens batem" }} com a nota</span>
          <span class="block text-sm font-normal text-muted-foreground" :title="matchedNames">{{ matchedNames }}</span>
        </span>
      </NuxtButton>
      <ul v-if="matchedExpanded" class="mt-2 grid grid-cols-1 gap-2">
        <li v-for="preview in view.matched" :key="`m-${preview.line.id}`">
          <NuxtButton
            size="xl"
            variant="outline"
            color="neutral"
            block
            class="justify-start text-left"
            @click="emit('open', preview.line.id)"
          >
            <span class="min-w-0 flex-1 text-sm font-semibold" :title="receiptLineLabel(preview)">{{ receiptLineLabel(preview) }}</span>
            <span class="shrink-0 text-xs font-normal text-muted-foreground tnum">{{ receiptSettledSummary(preview) }}</span>
          </NuxtButton>
        </li>
      </ul>
    </NuxtCard>
    <NuxtButton
      v-if="currentException"
      size="xl"
      variant="outline"
      color="error"
      block
      icon="i-lucide-undo-2"
      label="Devolver só este item"
      class="justify-center"
      :disabled="pending"
      data-reject-line
      @click="emit('reject-line', currentException.line.id)"
    />
  </section>
</template>
