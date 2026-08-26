<script setup lang="ts">
import type { POSCartItem } from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";
import { formatBRL } from "~/utils/posIntent";
import { globalKeysBlocked } from "~/utils/keyboardGuard";
import { clampPercent, clampQty, popDigit, pushDigit } from "~/presentation/numpad";
import { fireBarView, kitchenBadge, kitchenLineState } from "~/presentation/kitchen";
import { pruneSelection, selectionView, toggleSelected } from "~/presentation/selection";
import { pricingDiscountBadge } from "~/presentation/lineDiscounts";
import { toast } from "vue-sonner";

const props = defineProps<{
  items: POSCartItem[];
  requiresTab: boolean;
  hasOpenTab: boolean;
  loading: boolean;
  saving: boolean;
  /** Kitchen handoff affordances (Projection `Action`s) — labels, not invented. */
  fireAction: ActionAffordance;
  unfireAction: ActionAffordance;
  firing: boolean;
  discountReasons?: Array<{ ref: string; label?: string } | string>;
}>();

const emit = defineEmits<{
  increment: [string];
  decrement: [string];
  remove: [string];
  /** "Desfazer" do toast de remoção: devolve a linha exatamente como estava. */
  restore: [POSCartItem];
  setQty: [string, number];
  /** Observação da linha (padrão Odoo Note): viaja no intent e chega ao KDS. */
  setNotes: [string, string];
  setDiscount: [string, number, string];
  /** Operator unit-price override (numpad "Preço"); gated by manager approval. */
  setPrice: [string, number];
  prepare: [];
  move: [];
  fire: [];
  unfire: [string];
  /** Multi-select batch (spec §2.2): fire/unfire exactly these cart skus. The
   *  shell resolves their fresh server line_ids (regenerated on save). */
  fireLines: [string[]];
  unfireLines: [string[]];
  requestTab: [];
}>();

// Multi-select (spec §2.2): selection is screen state (a set of cart skus); the
// batch toolbar is shaped purely (presentation/selection). Tapping a line's
// checkbox toggles it without arming the numpad; the toolbar acts on all chosen.
const selected = ref<Set<string>>(new Set());
const selection = computed(() => selectionView(props.items, selected.value));
const selectMode = computed(() => selection.value.count > 0);
function isSelected(sku: string) {
  return selected.value.has(sku);
}
function toggleSelect(sku: string) {
  selected.value = toggleSelected(selected.value, sku);
}
function clearSelection() {
  selected.value = new Set();
}
// Keep the selection consistent when the cart changes (removed lines drop out).
watch(
  () => props.items.map((item) => item.sku).join("|"),
  () => { selected.value = pruneSelection(selected.value, props.items); },
);
function batchFire() {
  if (selection.value.canFire) emit("fireLines", selection.value.skus);
  clearSelection();
}
function batchUnfire() {
  if (selection.value.canUnfire) emit("unfireLines", selection.value.skus);
  clearSelection();
}
// Remover o LOTE é gesto largo: confirma antes (a seleção pode ter linha já
// enviada à cozinha e o operador pode ter marcado a mais).
function batchRemove() {
  const skus = selection.value.skus;
  if (!skus.length) return;
  const hasFired = skus.some((sku) => props.items.find((item) => item.sku === sku)?.fired);
  confirmAction.value = { kind: "batch", skus, hasFired };
}

// Kitchen handoff (spec §2.5): the fire bar and per-line state are shaped from
// the Projection's Actions + per-line `fired`, never decided here.
const fireBar = computed(() => fireBarView({
  items: props.items,
  affordance: props.fireAction,
  hasOpenTab: props.hasOpenTab,
  busy: props.loading || props.firing,
}));
function lineKitchenState(item: POSCartItem) {
  return kitchenLineState(item, { canUnfire: props.unfireAction.present });
}

// Cor só onde tem significado (PDV neutro): pronto é verde, cancelado é
// vermelho, o resto é cinza como toda a tela.
function badgeTone(tone: "neutral" | "success" | "destructive"): string {
  if (tone === "success") return "bg-success/10 text-success";
  if (tone === "destructive") return "bg-destructive/10 text-destructive";
  return "bg-muted text-muted-foreground";
}
function badgeIcon(tone: "neutral" | "success" | "destructive"): string {
  if (tone === "success") return "lucide:check";
  if (tone === "destructive") return "lucide:x";
  return "lucide:flame";
}


// Interim local total — reflects per-line manual discount as an estimate so the
// operator sees the discount land. Backend review remains the authoritative total.
const totalDisplay = computed(() => formatBRL(props.items.reduce((sum, item) => {
  const gross = item.price_q * item.qty;
  const perUnit = item.discount?.value ? Math.min(item.price_q, Math.round(item.price_q * item.discount.value / 100)) : 0;
  return sum + Math.max(0, gross - perUnit * item.qty);
}, 0)));
// Numpad targets the selected line. Three modes (Odoo's Qty/%/Price): "qty"
// (integer, first digit replaces), "disc" (percent), "price" (unit-price override
// — decimal entry, reais first, comma → centavos; flips manager approval on).
const MAX_QTY = 999;
const selectedSku = ref("");
const numpadBuffer = ref("");
const numpadFresh = ref(true);
const numpadMode = ref<"qty" | "disc" | "price">("qty");

const defaultReasons = [
  { ref: "cortesia", label: "Cortesia" },
  { ref: "fidelidade", label: "Fidelidade" },
  { ref: "qualidade", label: "Qualidade" },
];
const reasonOptions = computed(() => {
  const raw = props.discountReasons;
  if (raw?.length) {
    return raw.map((r) => (typeof r === "string" ? { ref: r, label: r } : { ref: r.ref, label: r.label || r.ref }));
  }
  return defaultReasons;
});
const discountReason = ref("");

// The numpad always targets a line: the explicitly selected one, or — when none
// is selected — the last added/edited line. So a single-item ticket is editable
// without tapping it first.
const activeSku = computed(() => {
  if (selectedSku.value && props.items.some((item) => item.sku === selectedSku.value)) {
    return selectedSku.value;
  }
  return props.items[props.items.length - 1]?.sku ?? "";
});
const activeItem = computed(() => props.items.find((item) => item.sku === activeSku.value) || null);

function qtyOf(sku: string): number {
  return props.items.find((item) => item.sku === sku)?.qty || 0;
}

function syncBufferToMode() {
  numpadFresh.value = true;
  if (numpadMode.value === "qty") {
    numpadBuffer.value = String(qtyOf(activeSku.value));
  } else if (numpadMode.value === "price") {
    const item = activeItem.value;
    numpadBuffer.value = item ? (item.price_q / 100).toFixed(2).replace(".", ",") : "";
  } else {
    const item = activeItem.value;
    numpadBuffer.value = item?.discount?.value ? String(item.discount.value) : "";
    discountReason.value = item?.discount?.reason || reasonOptions.value[0]?.ref || "cortesia";
  }
}

watch(activeSku, () => syncBufferToMode());
watch(numpadMode, () => syncBufferToMode());

function selectLine(sku: string) {
  selectedSku.value = sku;
  syncBufferToMode();
}

function setMode(mode: "qty" | "disc" | "price") {
  numpadMode.value = mode;
}

// Observação da linha (Odoo Note): diálogo simples de texto para a linha ativa.
// O dado já existia (POSCartItem.notes, intent, KDS) — só faltava quem editasse.
const noteDialog = ref<{ sku: string; name: string; text: string } | null>(null);
function openNoteDialog() {
  const item = activeItem.value;
  if (!item) return;
  noteDialog.value = { sku: item.sku, name: item.name, text: item.notes || "" };
}
function saveNote() {
  const dialog = noteDialog.value;
  noteDialog.value = null;
  if (!dialog) return;
  emit("setNotes", dialog.sku, dialog.text.trim());
}

// Remover item PERGUNTA, sempre. Já foi "direto com Desfazer", e o balcão
// discordou: o gesto que mais remove é o backspace zerando a quantidade, e ali
// ninguém teve intenção de excluir — o item sumia e o operador ficava
// procurando um toast que já tinha passado. Um modal custa um toque; recontar o
// pedido do cliente custa a venda.
const confirmAction = ref<
  | { kind: "line"; sku: string; name: string; fired: boolean }
  | { kind: "batch"; skus: string[]; hasFired: boolean }
  | null
>(null);
const confirmTitle = computed(() => {
  const action = confirmAction.value;
  if (!action) return "";
  if (action.kind === "batch") {
    return action.skus.length === 1 ? "Remover o item selecionado?" : `Remover ${action.skus.length} itens selecionados?`;
  }
  // Item já na cozinha é outra conversa: sair da tela não o tira do fogão.
  return action.fired ? "Remover item enviado à cozinha?" : `Remover ${action.name}?`;
});
const confirmCta = computed(() =>
  confirmAction.value?.kind === "batch" && confirmAction.value.skus.length > 1 ? "Remover itens" : "Remover item",
);
function askRemove(sku: string) {
  const item = props.items.find((entry) => entry.sku === sku);
  if (!item) return;
  confirmAction.value = {
    kind: "line",
    sku,
    name: item.name || "item",
    fired: Boolean(item.fired),
  };
}
/** O "Desfazer" continua existindo depois do SIM: confirmar não torna o engano
 *  impossível, só deliberado. */
function removeWithUndo(item: POSCartItem) {
  const snapshot: POSCartItem = { ...item };
  if (selectedSku.value === item.sku) selectedSku.value = "";
  emit("remove", item.sku);
  toast(`${snapshot.name} removido.`, {
    action: { label: "Desfazer", onClick: () => emit("restore", snapshot) },
  });
}
function cancelConfirm() {
  confirmAction.value = null;
}
function runConfirm() {
  const action = confirmAction.value;
  confirmAction.value = null;
  if (!action) return;
  if (action.kind === "batch") {
    action.skus.forEach((sku) => emit("remove", sku));
    clearSelection();
    return;
  }
  const item = props.items.find((entry) => entry.sku === action.sku);
  if (item) removeWithUndo(item);
}

function commitQty() {
  const sku = activeSku.value;
  if (!sku) return;
  const next = clampQty(numpadBuffer.value, MAX_QTY);
  if (next <= 0) {
    askRemove(sku);
    return;
  }
  emit("setQty", sku, next);
}

// Discount targets: the whole selection in multi-select, else the active line.
const discountTargets = computed(() => (selectMode.value ? selection.value.skus : (activeSku.value ? [activeSku.value] : [])));

function commitDiscount() {
  const targets = discountTargets.value;
  if (!targets.length) return;
  const value = clampPercent(numpadBuffer.value);
  targets.forEach((sku) => emit("setDiscount", sku, value, discountReason.value || "cortesia"));
}

// In multi-select the numpad is discount-only (batch quantity is meaningless).
const numpadCanType = computed(() => (numpadMode.value === "disc" ? discountTargets.value.length > 0 : !!activeSku.value));
// O que o pad está editando, para os rótulos de leitor de tela acompanharem o modo.
const numpadSubject = computed(() =>
  numpadMode.value === "disc" ? "desconto" : numpadMode.value === "price" ? "preço" : "quantidade",
);

// Price mode = decimal money entry (reais first, comma → centavos, ≤2 places).
function priceEntryToQ(entry: string): number {
  const n = Number.parseFloat((entry || "0").replace(",", "."));
  return Number.isFinite(n) && n >= 0 ? Math.min(99_999_999, Math.round(n * 100)) : 0;
}
function commitPrice() {
  if (activeSku.value) emit("setPrice", activeSku.value, priceEntryToQ(numpadBuffer.value));
}

function onDigit(digit: string) {
  if (!numpadCanType.value) return;
  if (numpadMode.value === "price") {
    const entry = numpadFresh.value ? "" : numpadBuffer.value;
    if (entry.includes(",")) {
      if ((entry.split(",")[1] ?? "").length >= 2) return;
    } else if (entry.replace(/^0+/, "").length >= 6) {
      return;
    }
    numpadBuffer.value = entry + digit;
    numpadFresh.value = false;
    commitPrice();
    return;
  }
  numpadBuffer.value = pushDigit(numpadBuffer.value, digit, { fresh: numpadFresh.value, maxLength: 3 });
  numpadFresh.value = false;
  if (numpadMode.value === "qty") commitQty();
  else commitDiscount();
}

// The comma key (price mode only): switch to centavos.
function onComma() {
  if (numpadMode.value !== "price" || !numpadCanType.value) return;
  let entry = numpadFresh.value ? "0" : (numpadBuffer.value || "0");
  if (!entry.includes(",")) entry += ",";
  numpadBuffer.value = entry;
  numpadFresh.value = false;
  commitPrice();
}

function onBackspace() {
  if (!numpadCanType.value) return;
  if (numpadMode.value === "price") {
    numpadBuffer.value = (numpadFresh.value ? "" : numpadBuffer.value).slice(0, -1);
    numpadFresh.value = false;
    commitPrice();
    return;
  }
  numpadBuffer.value = popDigit(numpadBuffer.value);
  numpadFresh.value = false;
  if (numpadMode.value === "qty") commitQty();
  else commitDiscount();
}

function onClear() {
  if (numpadMode.value === "qty") {
    if (activeSku.value) askRemove(activeSku.value);
    return;
  }
  if (numpadMode.value === "price") {
    numpadBuffer.value = "";
    numpadFresh.value = true;
    commitPrice();
    return;
  }
  const targets = discountTargets.value;
  if (!targets.length) return;
  numpadBuffer.value = "";
  numpadFresh.value = true;
  targets.forEach((sku) => emit("setDiscount", sku, 0, discountReason.value || "cortesia"));
}

function pickReason(reason: string) {
  discountReason.value = reason;
  if (numpadMode.value === "disc" && discountTargets.value.length) commitDiscount();
}

// Entering multi-select switches the numpad to its discount (batch) mode, since
// batch quantity has no meaning; leaving it restores quantity entry.
watch(selectMode, (on) => {
  numpadMode.value = on ? "disc" : "qty";
  numpadBuffer.value = "";
  numpadFresh.value = true;
});

function bump(sku: string, emitName: "increment" | "decrement") {
  selectedSku.value = sku;
  if (emitName === "decrement") {
    if (qtyOf(sku) <= 1) {
      askRemove(sku);
      return;
    }
    emit("decrement", sku);
    return;
  }
  emit("increment", sku);
}

// Physical keyboard feeds the active line (Odoo-style): select/add a product,
// then type a number to set its quantity. Ignored while typing in a field — e
// DESLIGADO com o terminal travado ou um diálogo aberto (globalKeysBlocked):
// a página segue montada sob o overlay, e o crachá/PIN digitado ali reescrevia
// quantidades e salvava no servidor.
function onWindowKeydown(event: KeyboardEvent) {
  if (globalKeysBlocked()) return;
  const target = event.target as HTMLElement | null;
  const editing = !!target
    && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
  if (editing || !props.items.length || !activeSku.value) return;
  if (event.key >= "0" && event.key <= "9") {
    event.preventDefault();
    onDigit(event.key);
  } else if (event.key === "Backspace") {
    event.preventDefault();
    onBackspace();
  }
}
onMounted(() => window.addEventListener("keydown", onWindowKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onWindowKeydown));
</script>

<template>
  <UiCard v-if="requiresTab && !hasOpenTab" class="gap-4 rounded-md p-4 shadow-none md:h-full md:min-h-0">
    <div class="grid gap-3 text-center">
      <div class="mx-auto grid size-11 place-items-center rounded-md border bg-muted">
        <Icon name="lucide:receipt-text" class="size-5 text-muted-foreground" />
      </div>
      <div class="grid gap-1">
        <p class="text-base font-semibold">Abra uma comanda</p>
        <p class="text-sm text-muted-foreground">
          Escolha uma comanda para este atendimento não se perder.
        </p>
      </div>
      <UiButton type="button" :disabled="loading" @click="$emit('requestTab')">
        Escolher comanda
      </UiButton>
    </div>
  </UiCard>

  <UiCard v-else class="gap-2.5 rounded-md p-3 shadow-none md:flex md:h-full md:min-h-0 md:flex-col md:overflow-hidden">
    <div class="min-h-24 overflow-auto pr-1 md:min-h-0 md:flex-1">
      <p v-if="!items.length" class="grid h-full min-h-24 place-items-center rounded-md border border-dashed p-4 text-center text-sm text-muted-foreground">
        Carrinho vazio
      </p>
      <ul v-else class="grid gap-0.5">
        <li
          v-for="item in items"
          :key="item.sku"
          class="grid cursor-pointer grid-cols-[auto_1fr_auto] items-center gap-2 rounded-md border border-transparent px-2 py-1 transition"
          :class="isSelected(item.sku) ? 'border-primary bg-primary/10' : (activeSku === item.sku ? 'border-primary bg-primary/5' : 'hover:bg-accent/60')"
          :aria-current="activeSku === item.sku ? 'true' : undefined"
          @click="selectLine(item.sku)"
        >
          <button
            type="button"
            class="grid size-6 shrink-0 place-items-center rounded-md border transition"
            :class="isSelected(item.sku) ? 'border-primary bg-primary text-primary-foreground' : 'border-border text-transparent hover:border-primary/60'"
            :aria-label="`Selecionar ${item.name}`"
            :aria-pressed="isSelected(item.sku)"
            @click.stop="toggleSelect(item.sku)"
          >
            <Icon name="lucide:check" class="size-4" />
          </button>
          <div class="min-w-0">
            <p class="truncate text-sm font-medium leading-tight">{{ item.name }}</p>
            <p class="text-xs tabular-nums" :class="item.price_overridden ? 'text-primary' : 'text-muted-foreground'">
              <Icon v-if="item.price_overridden" name="lucide:pencil" class="mr-0.5 inline size-3 align-[-1px]" />{{ item.qty }}× {{ formatBRL(item.price_q) }} · {{ formatBRL(item.qty * item.price_q) }}
            </p>
            <p v-if="item.notes" class="flex items-center gap-1 truncate text-xs italic text-muted-foreground">
              <Icon name="lucide:sticky-note" class="size-3 shrink-0" />
              <span class="truncate">{{ item.notes }}</span>
            </p>
            <!-- Desconto automático de pricing (lote/liquidação, happy hour,
                 funcionário): o preço da linha JÁ vem reduzido; o badge diz por quê. -->
            <span
              v-if="pricingDiscountBadge(item)"
              class="mt-0.5 inline-flex w-fit items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
              :title="`Desconto automático: ${pricingDiscountBadge(item)}`"
            >
              <Icon name="lucide:tags" class="size-3" />
              {{ pricingDiscountBadge(item) }}
            </span>
            <span
              v-if="item.discount && item.discount.value > 0"
              class="mt-0.5 inline-flex w-fit items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
              :title="`Desconto: ${item.discount.reason}`"
            >
              <Icon name="lucide:tag" class="size-3" />
              −{{ item.discount.value }}% · {{ item.discount.reason }}
            </span>
            <button
              v-if="lineKitchenState(item) === 'fired_cancellable'"
              type="button"
              class="group mt-0.5 inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
              :disabled="firing"
              :aria-label="`${unfireAction.label}: ${item.name}`"
              @click.stop="$emit('unfire', item.line_id || '')"
            >
              <Icon name="lucide:flame" class="size-3 group-hover:hidden" />
              <Icon name="lucide:x" class="hidden size-3 group-hover:inline" />
              {{ kitchenBadge(item).label }}
            </button>
            <span
              v-else-if="lineKitchenState(item) === 'fired'"
              class="mt-0.5 inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium"
              :class="badgeTone(kitchenBadge(item).tone)"
              aria-live="polite"
            >
              <Icon :name="badgeIcon(kitchenBadge(item).tone)" class="size-3" />
              {{ kitchenBadge(item).label }}
            </span>
          </div>
          <!-- Alvos de toque de balcão: steppers em icon-sm (36px), e a lixeira
               APARTADA deles, para o dedo apressado não remover querendo "menos 1". -->
          <div class="flex items-center gap-1" @click.stop>
            <UiButton variant="ghost" size="icon-sm" aria-label="Diminuir" @click="bump(item.sku, 'decrement')">
              <Icon name="lucide:minus" class="size-4" />
            </UiButton>
            <span class="w-6 text-center text-sm font-semibold tabular-nums">{{ item.qty }}</span>
            <UiButton variant="ghost" size="icon-sm" aria-label="Aumentar" @click="bump(item.sku, 'increment')">
              <Icon name="lucide:plus" class="size-4" />
            </UiButton>
            <UiButton variant="ghost" size="icon-sm" class="ml-2" aria-label="Remover" @click="askRemove(item.sku)">
              <Icon name="lucide:trash-2" class="size-4 text-destructive" />
            </UiButton>
          </div>
        </li>
      </ul>
    </div>

    <div v-if="items.length" class="grid shrink-0 gap-1.5">
      <!-- Batch toolbar (multi-select §2.2): acts on every checked line via Actions. -->
      <div v-if="selectMode" class="flex flex-wrap items-center gap-1.5 rounded-md border border-primary/30 bg-primary/5 p-1.5">
        <span class="px-1 text-xs font-semibold tabular-nums">{{ selection.count }} selec.</span>
        <UiButton v-if="selection.canFire" size="xs" variant="outline" class="gap-1" :disabled="firing" @click="batchFire">
          <Icon name="lucide:utensils" class="size-3.5" />
          {{ fireAction.label || "Enviar" }}
        </UiButton>
        <UiButton v-if="selection.canUnfire" size="xs" variant="outline" class="gap-1" :disabled="firing" @click="batchUnfire">
          <Icon name="lucide:x" class="size-3.5" />
          {{ unfireAction.label || "Cancelar envio" }}
        </UiButton>
        <UiButton size="xs" variant="outline" class="gap-1 text-destructive" :disabled="loading" @click="batchRemove">
          <Icon name="lucide:trash-2" class="size-3.5" />
          Remover
        </UiButton>
        <UiButton size="xs" variant="ghost" class="ml-auto" aria-label="Limpar seleção" title="Limpar seleção" @click="clearSelection">
          <Icon name="lucide:x" class="size-4" />
        </UiButton>
      </div>

      <div v-if="!selectMode" class="flex gap-1">
        <button
          type="button"
          class="flex-1 rounded-md border py-1.5 text-sm font-medium transition"
          :class="numpadMode === 'qty' ? 'border-primary bg-primary/5' : 'hover:bg-accent'"
          @click="setMode('qty')"
        >
          Qtd
        </button>
        <button
          type="button"
          class="flex-1 rounded-md border py-1.5 text-sm font-medium transition"
          :class="numpadMode === 'disc' ? 'border-primary bg-primary/5' : 'hover:bg-accent'"
          @click="setMode('disc')"
        >
          Desc %
        </button>
        <button
          type="button"
          class="flex-1 rounded-md border py-1.5 text-sm font-medium transition"
          :class="numpadMode === 'price' ? 'border-primary bg-primary/5' : 'hover:bg-accent'"
          @click="setMode('price')"
        >
          Preço
        </button>
        <button
          type="button"
          class="flex-1 rounded-md border py-1.5 text-sm font-medium transition"
          :class="activeItem?.notes ? 'border-primary bg-primary/5' : 'hover:bg-accent'"
          :disabled="!activeItem"
          @click="openNoteDialog"
        >
          Obs.
        </button>
      </div>
      <p v-else class="px-1 text-xs font-medium text-muted-foreground">
        Desconto em {{ selection.count }} {{ selection.count === 1 ? "item selecionado" : "itens selecionados" }} — digite o %
      </p>
      <div v-if="numpadMode === 'disc' && discountTargets.length" class="flex flex-wrap gap-1">
        <button
          v-for="reason in reasonOptions"
          :key="reason.ref"
          type="button"
          class="rounded-full border px-2.5 py-0.5 text-xs transition"
          :class="discountReason === reason.ref ? 'border-primary bg-primary/5 font-medium' : 'hover:bg-accent'"
          @click="pickReason(reason.ref)"
        >
          {{ reason.label }}
        </button>
      </div>
      <!-- price mode: a comma key for centavos (the shared numpad is integer-only) -->
      <div v-if="numpadMode === 'price' && !selectMode" class="flex items-center gap-1">
        <span class="flex-1 px-1 text-xs text-muted-foreground">Preço unitário — vírgula p/ centavos · gerente aprova</span>
        <button
          type="button"
          class="rounded-md border bg-card px-4 py-1.5 text-base font-semibold transition hover:bg-accent active:translate-y-px disabled:opacity-40"
          :disabled="!numpadCanType"
          aria-label="Vírgula (centavos)"
          @click="onComma"
        >
          ,
        </button>
      </div>
      <OperatorNumpad
        compact
        :disabled="!items.length"
        :subject="numpadSubject"
        @digit="onDigit"
        @backspace="onBackspace"
        @clear="onClear"
      />
    </div>

    <div class="grid shrink-0 gap-2 border-t pt-2.5">
      <div class="flex items-baseline justify-between">
        <span class="text-sm font-medium text-muted-foreground">Total parcial</span>
        <strong class="text-xl tabular-nums">{{ totalDisplay }}</strong>
      </div>
      <!-- Secondary actions stack on the left; Pagamento is the highlight column
           spanning their full height — saves a vertical row. -->
      <div v-if="fireBar.visible || (hasOpenTab && items.length)" class="grid grid-cols-2 gap-2">
        <div class="flex flex-col gap-2">
          <UiButton
            v-if="fireBar.visible"
            variant="outline"
            class="justify-center gap-2"
            :disabled="fireBar.disabled"
            :loading="firing"
            @click="$emit('fire')"
          >
            <Icon name="lucide:utensils" class="size-4" />
            {{ fireBar.label }}
          </UiButton>
          <UiButton
            v-if="hasOpenTab && items.length"
            variant="outline"
            class="justify-center gap-1.5"
            :disabled="loading"
            @click="$emit('move')"
          >
            <Icon name="lucide:split" class="size-4" />
            Mover itens
          </UiButton>
        </div>
        <UiButton
          size="lg"
          class="h-full flex-col gap-1 text-base"
          :disabled="!items.length || loading"
          :loading="loading"
          @click="$emit('prepare')"
        >
          <Icon name="lucide:credit-card" class="size-6" />
          Pagamento
          <kbd class="rounded border border-primary-foreground/30 bg-transparent px-1.5 py-0.5 font-mono text-xs font-medium opacity-80" aria-hidden="true">F4</kbd>
        </UiButton>
      </div>
      <UiButton
        v-else
        size="lg"
        class="w-full gap-2"
        :disabled="!items.length || loading"
        :loading="loading"
        @click="$emit('prepare')"
      >
        <Icon name="lucide:credit-card" class="size-5" />
        Pagamento
        <kbd class="rounded border border-primary-foreground/30 bg-transparent px-1.5 py-0.5 font-mono text-xs font-medium opacity-80" aria-hidden="true">F4</kbd>
      </UiButton>
    </div>
  </UiCard>

  <UiDialog :open="!!noteDialog" @update:open="(value) => { if (!value) noteDialog = null; }">
    <UiDialogContent class="sm:max-w-sm">
      <UiDialogHeader>
        <UiDialogTitle>Observação · {{ noteDialog?.name }}</UiDialogTitle>
        <UiDialogDescription>A observação sai junto com o item para a cozinha.</UiDialogDescription>
      </UiDialogHeader>
      <UiTextarea
        v-if="noteDialog"
        v-model="noteDialog.text"
        :rows="3"
        placeholder="Ex: sem cebola, bem passado"
        autofocus
      />
      <UiDialogFooter class="gap-2">
        <UiButton variant="outline" @click="noteDialog = null">Cancelar</UiButton>
        <UiButton @click="saveNote">Salvar observação</UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>

  <UiDialog :open="!!confirmAction" @update:open="(value) => { if (!value) cancelConfirm(); }">
    <UiDialogContent class="sm:max-w-sm">
      <UiDialogHeader>
        <UiDialogTitle>{{ confirmTitle }}</UiDialogTitle>
        <UiDialogDescription v-if="confirmAction?.kind === 'line' && confirmAction.fired">
          <strong>{{ confirmAction.name }}</strong> já foi enviado à cozinha. Remover tira a linha do pedido; avise o preparo se necessário.
        </UiDialogDescription>
        <UiDialogDescription v-else-if="confirmAction?.kind === 'line'">
          A linha sai do pedido. Dá para desfazer logo depois.
        </UiDialogDescription>
        <UiDialogDescription v-else-if="confirmAction?.kind === 'batch'">
          {{ confirmAction.hasFired
            ? "As linhas selecionadas saem do pedido, inclusive as que já foram à cozinha."
            : "As linhas selecionadas saem do pedido." }}
        </UiDialogDescription>
      </UiDialogHeader>
      <UiDialogFooter class="gap-2">
        <UiButton variant="outline" @click="cancelConfirm">Cancelar</UiButton>
        <UiButton variant="destructive" @click="runConfirm">{{ confirmCta }}</UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
