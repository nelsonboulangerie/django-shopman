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
 * incontornável". Três passos, na ordem em que a doca acontece:
 *
 * 1. **Tudo bate com a nota** + **Contei os volumes**: o único ato físico, o
 *    fato que só o recebedor vê. As linhas que batem entram sem o ok de cada uma.
 * 2. **Falta só a validade**: uma linha perecível por vez, com atalhos de um
 *    toque (a da última entrega, a típica do insumo) e "Outra data".
 * 3. **Para resolver**: só o item que não bate, aberto na gaveta dele.
 *
 * "Ler da embalagem" (câmera lendo data e lote) NÃO está aqui: a casa ainda não
 * tem leitor de data/lote na tela de receber. Fica como próximo passo.
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
}>();

const emit = defineEmits<{
  count: [counted: number | null];
  expiry: [lineId: string, date: string];
  open: [lineId: string];
}>();

const todayIso = todayIsoDate();

// O stepper nasce no número esperado: contar e bater é o caso comum, e o
// recebedor só mexe quando a doca diz outra coisa.
const draftCount = ref<number>(props.view.countedVolumes ?? props.view.expectedVolumes ?? 0);
watch(
  () => props.view.expectedVolumes,
  (expected) => {
    if (props.view.countedVolumes === null && expected !== null) draftCount.value = expected;
  },
);
watch(
  () => props.view.countedVolumes,
  (counted) => {
    if (counted !== null) draftCount.value = counted;
  },
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

const volumesSource = computed(() =>
  props.declaredVolumes > 0 ? `A nota diz ${props.view.expectedVolumes} volumes (caixas, sacos, fardos)`
  : `As embalagens da nota somam ${props.view.expectedVolumes} volumes`,
);

const headline = computed(() =>
  props.view.exceptions.length === 0 ? "Tudo bate com a nota"
  : `${props.view.matched.length} ${props.view.matched.length === 1 ? "bate" : "batem"} · ${props.view.exceptions.length} para resolver`,
);

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

function exceptionDigest(preview: ReceiptLinePreview): string {
  const difference = receiptLineDifference(preview.line);
  if (difference) {
    const unit = preview.purchaseUnitLabel || preview.material.unit;
    return `Nota ${difference.invoiceQty} · chegou ${difference.arrivedQty} ${unit}`;
  }
  return preview.nextStep || (preview.line.checked ? "Conferido" : "Conferir e marcar como conferido");
}
</script>

<template>
  <!-- Desenho da prévia v4 (`compras-validade4.html`): o veredito do sistema num cartão
       verde (ou âmbar), o ato da vez com borda cheia na cor do app, atalhos de 48px,
       stepper de 56px e as linhas resolvidas em verde leve com "Trocar". -->
  <section class="space-y-3" aria-label="Conferência por exceção">
    <!-- 1. O que o sistema já sabe: a nota e quanto dela bate. -->
    <div
      class="rounded-2xl border p-4"
      :class="view.exceptions.length === 0 ? 'border-success/35 bg-success/8' : 'border-warning/40 bg-warning/8'"
      data-exception-verdict
    >
      <div class="flex items-start gap-3">
        <span
          class="grid size-11 shrink-0 place-items-center rounded-full text-white"
          :class="view.exceptions.length === 0 ? 'bg-success' : 'bg-warning'"
        >
          <Icon :name="view.exceptions.length === 0 ? 'lucide:check-check' : 'lucide:triangle-alert'" class="size-6" />
        </span>
        <div class="min-w-0 flex-1">
          <h2 class="text-[19px] leading-snug font-semibold">{{ headline }}</h2>
          <p class="mt-0.5 op-body tnum">
            {{ lineCount }} {{ lineCount === 1 ? "item" : "itens" }}<template v-if="totalCostQ > 0"> · {{ formatMoney(totalCostQ) }}</template>
          </p>
        </div>
      </div>
      <p v-if="view.matched.length" class="mt-3 flex items-start gap-2 text-[14px] leading-[22px] text-foreground/85">
        <Icon name="lucide:sparkles" class="mt-1 size-4 shrink-0 text-muted-foreground" />
        Bate com a nota quando o item é o do de-para, a embalagem confere com o cadastro e a quantidade e o valor são os da nota.
      </p>
    </div>

    <!-- 2. O único ato físico: contar os volumes. -->
    <div
      v-if="view.available"
      data-receipt-anchor="volumes"
      class="scroll-mt-4 rounded-2xl bg-card p-4 transition-shadow"
      :class="[countMismatch ? 'border-2 border-destructive' : view.countOk ? 'border border-success/40' : 'border-2 border-primary', volumesRing]"
    >
      <p class="op-eyebrow" :class="countMismatch ? 'text-destructive' : view.countOk ? 'text-success' : 'text-primary'">O que só você vê</p>
      <h3 class="mt-1 text-[18px] leading-snug font-semibold">Contei os volumes</h3>
      <p class="op-label font-normal text-muted-foreground">{{ volumesSource }}</p>

      <div class="mt-3 flex items-center gap-3">
        <button
          type="button"
          class="grid size-14 shrink-0 place-items-center rounded-[14px] border border-border bg-card hover:bg-accent disabled:opacity-50"
          aria-label="Um volume a menos"
          :disabled="pending || draftCount <= 0"
          @click="stepCount(-1)"
        >
          <Icon name="lucide:minus" class="size-6" />
        </button>
        <div
          class="flex h-16 min-w-0 flex-1 items-center justify-center gap-1.5 rounded-xl border tnum"
          :class="countMatches ? 'border-success/40 bg-success/8' : 'border-warning/40 bg-warning/8'"
          aria-live="polite"
        >
          <span class="text-[34px] leading-none font-semibold">{{ draftCount }}</span>
          <span class="text-[17px] font-medium text-muted-foreground">de {{ view.expectedVolumes }}</span>
          <Icon v-if="countMatches" name="lucide:circle-check" class="ml-1 size-5 text-success" />
        </div>
        <button
          type="button"
          class="grid size-14 shrink-0 place-items-center rounded-[14px] border border-border bg-card hover:bg-accent disabled:opacity-50"
          aria-label="Um volume a mais"
          :disabled="pending"
          @click="stepCount(1)"
        >
          <Icon name="lucide:plus" class="size-6" />
        </button>
      </div>

      <button
        v-if="!countDeclared"
        type="button"
        class="mt-3 inline-flex h-14 w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 op-action text-primary-foreground disabled:opacity-50"
        :disabled="pending || draftCount <= 0"
        @click="emit('count', draftCount)"
      >
        <Icon name="lucide:check" class="size-5" />
        Contei {{ draftCount }} {{ draftCount === 1 ? "volume" : "volumes" }}
      </button>
      <p
        v-else-if="view.countOk"
        class="mt-3 flex items-center gap-2 rounded-xl bg-success/10 px-3 py-2.5 op-label text-success"
      >
        <Icon name="lucide:circle-check-big" class="size-5 shrink-0" />
        {{ view.countedVolumes }} de {{ view.expectedVolumes }} volumes contados. Os itens que batem entram sem conferir um a um.
      </p>
      <p v-else class="mt-3 flex items-start gap-2 rounded-xl bg-destructive/10 px-3 py-2.5 op-label text-destructive">
        <Icon name="lucide:circle-alert" class="mt-0.5 size-5 shrink-0" />
        Contou {{ view.countedVolumes }} de {{ view.expectedVolumes }}. Abra o item que chegou diferente e corrija a quantidade que chegou.
      </p>

      <!-- Contagem que não fecha: a lista do que bate vira a lista de onde procurar. -->
      <ul v-if="countMismatch && view.matched.length" class="mt-3 grid gap-2">
        <li v-for="preview in view.matched" :key="`count-${preview.line.id}`">
          <button
            type="button"
            class="flex min-h-12 w-full min-w-0 items-center gap-2 rounded-xl border border-border bg-card px-3 text-left hover:bg-accent"
            @click="emit('open', preview.line.id)"
          >
            <span class="min-w-0 flex-1 truncate op-label font-semibold">{{ receiptLineLabel(preview) }}</span>
            <span class="shrink-0 op-micro text-muted-foreground tnum">{{ receiptSettledSummary(preview) }}</span>
            <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" />
          </button>
        </li>
      </ul>
    </div>

    <!-- 3. A validade é incontornável: uma linha perecível por vez. -->
    <div v-if="view.perishables.length" class="rounded-2xl border border-border bg-card p-4">
      <div class="flex items-baseline justify-between gap-2">
        <h3 class="text-[19px] leading-snug font-semibold">{{ view.nextExpiry ? "Falta só a validade" : "Validades" }}</h3>
        <span class="op-body font-semibold tnum">{{ view.expiryDone }} de {{ view.perishables.length }}</span>
      </div>
      <div class="mt-2 flex gap-1.5" aria-hidden="true">
        <span
          v-for="preview in view.perishables"
          :key="`bar-${preview.line.id}`"
          class="h-2 flex-1 rounded-full"
          :class="preview.line.expiryDate ? 'bg-success' : 'bg-primary/25'"
        />
      </div>

      <div v-if="currentExpiry" class="mt-3 rounded-2xl border-2 border-primary bg-card p-3" :data-receipt-expiry="currentExpiry.line.id">
        <div class="flex items-center gap-2.5">
          <span class="grid size-9 shrink-0 place-items-center rounded-full bg-primary/12 text-primary">
            <Icon name="lucide:calendar-clock" class="size-5" />
          </span>
          <div class="min-w-0 flex-1">
            <p class="truncate op-title">{{ receiptLineLabel(currentExpiry) }}</p>
            <p class="op-label font-normal text-muted-foreground tnum">{{ receiptSettledSummary(currentExpiry) }} · vence em quando?</p>
          </div>
        </div>
        <div class="mt-3 grid gap-2">
          <button
            v-for="(shortcut, index) in currentShortcuts"
            :key="shortcut.key"
            type="button"
            class="flex min-h-12 w-full items-center gap-2 rounded-xl border px-2.5 py-1.5 text-left hover:bg-accent disabled:opacity-50"
            :class="index === 0 ? 'border-primary/50 bg-primary/6' : 'border-border bg-card'"
            :disabled="pending"
            @click="chooseExpiry(currentExpiry.line.id, shortcut.date)"
          >
            <Icon :name="shortcut.key === 'last' ? 'lucide:history' : 'lucide:calendar-plus'" class="size-5 shrink-0" :class="index === 0 ? 'text-primary' : 'text-muted-foreground'" />
            <span class="flex-1 text-[14px] leading-[17px] font-semibold">{{ shortcut.label }}</span>
            <span class="text-[13px] leading-4 text-muted-foreground tnum">{{ shortcut.caption }}</span>
          </button>
          <button
            v-if="!otherDateOpen"
            type="button"
            class="flex min-h-12 w-full items-center gap-2 rounded-xl border border-border bg-card px-2.5 text-left text-[14px] font-semibold hover:bg-accent"
            @click="otherDateOpen = true"
          >
            <Icon name="lucide:calendar" class="size-5 shrink-0 text-muted-foreground" />
            Outra data
          </button>
          <OperatorDayPicker v-else v-model="otherDate" :today="todayIso" label="Validade" />
        </div>
        <p class="mt-2 op-label font-normal text-muted-foreground">Um toque grava e passa para o próximo.</p>
      </div>

      <ul v-if="expiryDoneList.length" class="mt-2 grid gap-2">
        <li
          v-for="preview in expiryDoneList"
          :key="`expiry-${preview.line.id}`"
          class="flex min-h-12 items-center gap-3 rounded-xl border border-success/30 bg-success/5 px-3 py-1.5"
        >
          <Icon name="lucide:circle-check-big" class="size-6 shrink-0 text-success" />
          <span class="min-w-0 flex-1">
            <span class="block truncate text-[15px] font-semibold">{{ receiptLineLabel(preview) }}</span>
            <span class="block op-label font-normal text-muted-foreground tnum">
              Vence {{ formatShortDate(preview.line.expiryDate) }}<template v-if="preview.line.expiryFromInvoice"> · veio na nota</template>
            </span>
          </span>
          <button
            type="button"
            class="inline-flex h-11 shrink-0 items-center rounded-full px-3 text-[14px] font-semibold text-primary hover:bg-accent"
            @click="swapExpiry(preview.line.id)"
          >
            Trocar
          </button>
        </li>
      </ul>
    </div>

    <!-- 4. Só o que não bate pede atenção, item a item. -->
    <div v-if="view.exceptions.length" class="rounded-2xl border-2 border-warning/60 bg-card p-4">
      <div class="flex items-center gap-2.5">
        <Icon name="lucide:triangle-alert" class="size-6 shrink-0 text-warning" />
        <h3 class="text-[18px] leading-snug font-semibold">Para resolver</h3>
      </div>
      <p class="mt-0.5 op-label font-normal text-muted-foreground">Estes itens não batem com a nota: cada um pede a sua conferência.</p>
      <ul class="mt-3 grid gap-2">
        <li v-for="preview in view.exceptions" :key="`exception-${preview.line.id}`">
          <button
            type="button"
            class="flex min-h-14 w-full min-w-0 items-center gap-3 rounded-xl border px-3 py-2 text-left hover:bg-accent"
            :class="preview.line.checked && !preview.nextStep ? 'border-success/30 bg-success/5' : 'border-warning/45 bg-card'"
            @click="emit('open', preview.line.id)"
          >
            <Icon
              :name="preview.line.checked && !preview.nextStep ? 'lucide:circle-check-big' : 'lucide:triangle-alert'"
              class="size-5 shrink-0"
              :class="preview.line.checked && !preview.nextStep ? 'text-success' : 'text-warning'"
            />
            <span class="min-w-0 flex-1">
              <span class="block truncate op-title">{{ receiptLineLabel(preview) }}</span>
              <span class="block truncate op-label font-normal text-muted-foreground tnum">{{ exceptionDigest(preview) }}</span>
            </span>
            <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground" />
          </button>
        </li>
      </ul>
    </div>
  </section>
</template>
