<script setup lang="ts">
import type { POSCartItem } from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";
import { formatBRL } from "~/utils/posIntent";
import { globalKeysBlocked } from "~/utils/keyboardGuard";
import {
  clampPercent,
  clampQty,
  popDigit,
  pushDigit,
} from "~/presentation/numpad";
import {
  fireBarView,
  kitchenBadge,
  type KitchenBadgeView,
  kitchenLineState,
} from "~/presentation/kitchen";
import {
  pruneSelection,
  selectionView,
  toggleSelected,
} from "~/presentation/selection";
import {
  lineDiscountBadge,
  lineListTotalDisplay,
  lineTotalQ,
  unitChargedQ,
} from "~/presentation/lineDiscounts";
import { cartNetTotalQ } from "~/presentation/receipt";
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

// ⚠️ Cada evento de linha carrega o `line_id`, nunca o sku. Com duas linhas do
// mesmo produto na comanda — que é o que este WP passou a permitir — o sku
// endereça as duas ao mesmo tempo: o desconto do segundo chá caía no primeiro e
// a observação aparecia nos dois.
const emit = defineEmits<{
  increment: [string];
  decrement: [string];
  remove: [string];
  /** "Desfazer" do toast de remoção: devolve a linha exatamente como estava. */
  restore: [POSCartItem];
  setQty: [string, number];
  /** Observação da linha (padrão Odoo Note): viaja no intent e chega ao KDS. */
  setNotes: [string, string];
  /** line_id, valor (% ou reais, conforme o formato), motivo, formato. */
  setDiscount: [string, number, string, "percent" | "fixed"];
  /** Operator unit-price override (numpad "Preço"); gated by manager approval. */
  prepare: [];
  move: [];
  fire: [];
  unfire: [string];
  /** Multi-select batch (spec §2.2): fire/unfire exatamente estas linhas. */
  fireLines: [string[], (success: boolean) => void];
  unfireLines: [string[], (success: boolean) => void];
  requestTab: [];
}>();

// Multi-select (spec §2.2): selection is screen state (um conjunto de
// `line_id`s); the batch toolbar is shaped purely (presentation/selection).
// Tapping a line's checkbox toggles it without arming the numpad; the toolbar
// acts on all chosen.
const selected = ref<Set<string>>(new Set());
const selection = computed(() => selectionView(props.items, selected.value));
const selectMode = computed(() => selection.value.count > 0);
function isSelected(lineId: string) {
  return selected.value.has(lineId);
}
function toggleSelect(lineId: string) {
  selected.value = toggleSelected(selected.value, lineId);
}
function clearSelection() {
  selected.value = new Set();
}
// Keep the selection consistent when the cart changes (removed lines drop out).
watch(
  () => props.items.map((item) => item.line_id).join("|"),
  () => {
    selected.value = pruneSelection(selected.value, props.items);
  },
);
const batchPending = ref(false);
function completeBatch(success: boolean) {
  batchPending.value = false;
  if (success) finishItemMode();
}
function batchFire() {
  if (
    props.loading ||
    props.saving ||
    props.firing ||
    batchPending.value ||
    !props.fireAction.present ||
    !props.fireAction.enabled
  )
    return;
  if (!selection.value.canFire) return;
  batchPending.value = true;
  emit("fireLines", selection.value.lineIds, completeBatch);
}
function batchUnfire() {
  if (
    props.loading ||
    props.saving ||
    props.firing ||
    batchPending.value ||
    !props.unfireAction.present ||
    !props.unfireAction.enabled
  )
    return;
  if (!selection.value.canUnfire) return;
  batchPending.value = true;
  emit("unfireLines", selection.value.lineIds, completeBatch);
}
// Remover o LOTE é gesto largo: confirma antes (a seleção pode ter linha já
// enviada à cozinha e o operador pode ter marcado a mais).
function batchRemove() {
  if (props.loading || props.saving) return;
  const lineIds = selection.value.lineIds;
  if (!lineIds.length) return;
  const hasFired = lineIds.some(
    (lineId) => props.items.find((item) => item.line_id === lineId)?.fired,
  );
  confirmAction.value = { kind: "batch", lineIds, hasFired };
}

// Kitchen handoff (spec §2.5): the fire bar and per-line state are shaped from
// the Projection's Actions + per-line `fired`, never decided here.
const fireBar = computed(() =>
  fireBarView({
    items: props.items,
    affordance: props.fireAction,
    hasOpenTab: props.hasOpenTab,
    busy: props.loading || props.firing,
  }),
);
function lineKitchenState(item: POSCartItem) {
  return kitchenLineState(item, { canUnfire: props.unfireAction.present });
}

// Cor só onde tem significado (PDV neutro): pronto é verde, cancelado é
// vermelho, o resto é cinza como toda a tela.
function badgeTone(tone: KitchenBadgeView["tone"]): string {
  if (tone === "success") return "bg-success/10 text-success";
  if (tone === "destructive") return "bg-destructive/10 text-destructive";
  // Divergência não é erro da cozinha nem cancelamento: é uma conta que não
  // fecha, e pede o âmbar de "olhe para isto", não o vermelho de "deu errado".
  if (tone === "warning")
    return "bg-warning/10 text-amber-800 dark:text-amber-300";
  return "bg-muted text-muted-foreground";
}

// O "Total parcial" — a MESMA soma da tela do cliente e do total interino do
// pagamento, por `cartNetTotalQ`. Esta conta estava escrita à mão aqui, uma
// TERCEIRA cópia dela (as outras em `receipt.ts` e `customerDisplay.ts`), e as
// três aplicavam por conta própria o percentual de desconto da linha — que o
// servidor descarta quando um desconto automático maior já ganhou. Resultado na
// tela: linha de R$ 10,20 e Total parcial de R$ 9,18, um debaixo do outro.
const totalDisplay = computed(() => formatBRL(cartNetTotalQ(props.items)));

/** O selo do desconto que venceu a linha. Usa `reasonOptions`, que normaliza a
 *  lista do servidor e cai nos motivos padrão: o selo diz "Cortesia", não o ref. */
function discountBadge(item: POSCartItem) {
  return (
    lineDiscountBadge(item, reasonOptions.value) ||
    (lineListTotalDisplay(item) ? "Desconto aplicado" : "")
  );
}
function compactDiscount(item: POSCartItem) {
  const label = discountBadge(item);
  return (label.match(/−.+$/)?.[0] || label).replace(/(\d)\.(\d)/g, "$1,$2");
}
// O teclado age sobre a linha selecionada, em três modos: "qty" (inteiro, o
// primeiro dígito substitui), "disc" (desconto em %) e "disc_brl" (desconto em
// R$ — entrada decimal, reais primeiro, vírgula → centavos).
//
// ⚠️ O terceiro modo era PREÇO: o operador digitava o preço unitário à mão. Ele
// saiu inteiro. Preço à mão não passava pela régua do desconto — não tinha
// limite da loja, não tinha motivo, não competia no "maior desconto ganha", não
// aparecia como desconto em lugar nenhum, e ainda CONGELAVA a linha contra
// reprecificação, com um portão de gerente só dele. Eram dois modelos
// concorrentes para a mesma pergunta ("quanto o cliente paga a menos"), e o
// segundo furava a régua do primeiro.
//
// O que ficou é o MESMO mecanismo em dois formatos: % ou R$, com motivo, com
// limite, e com o gerente sendo chamado pela mesma régua. A entrada decimal com
// vírgula é herança direta do modo preço — ela some do preço e reaparece aqui.
const MAX_QTY = 999;
const selectedLineId = ref("");
const expandedLineId = ref("");
const detailsPrefix = useId();
function detailsId(lineId: string) {
  return `${detailsPrefix}-${encodeURIComponent(lineId)}`;
}
function toggleDetails(lineId: string) {
  selectLine(lineId);
  expandedLineId.value = expandedLineId.value === lineId ? "" : lineId;
}
watch(
  () => props.items.map((item) => item.line_id),
  (ids) => {
    if (!ids.includes(expandedLineId.value)) expandedLineId.value = "";
  },
);
const numpadBuffer = ref("");
const numpadFresh = ref(true);
const numpadMode = ref<"qty" | "disc" | "disc_brl">("qty");
/** O formato que o teclado está digitando agora. */
const discountKind = computed<"percent" | "fixed">(() =>
  numpadMode.value === "disc_brl" ? "fixed" : "percent",
);
/** Os dois modos de desconto, para os guardas que não se importam com o formato. */
const inDiscountMode = computed(() => numpadMode.value !== "qty");

const defaultReasons = [
  { ref: "cortesia", label: "Cortesia" },
  { ref: "fidelidade", label: "Fidelidade" },
  { ref: "qualidade", label: "Qualidade" },
];
const reasonOptions = computed(() => {
  const raw = props.discountReasons;
  if (raw?.length) {
    return raw.map((r) =>
      typeof r === "string"
        ? { ref: r, label: r }
        : { ref: r.ref, label: r.label || r.ref },
    );
  }
  return defaultReasons;
});
const discountReason = ref("");

// The numpad always targets a line: the explicitly selected one, or — when none
// is selected — the last added/edited line. So a single-item ticket is editable
// without tapping it first.
const activeLineId = computed(() => {
  if (
    selectedLineId.value &&
    props.items.some((item) => item.line_id === selectedLineId.value)
  ) {
    return selectedLineId.value;
  }
  return props.items[props.items.length - 1]?.line_id ?? "";
});
const activeItem = computed(
  () => props.items.find((item) => item.line_id === activeLineId.value) || null,
);

function qtyOf(lineId: string): number {
  return props.items.find((item) => item.line_id === lineId)?.qty || 0;
}

function syncBufferToMode() {
  numpadFresh.value = true;
  if (numpadMode.value === "qty") {
    numpadBuffer.value = String(qtyOf(activeLineId.value));
    return;
  }
  const item = activeItem.value;
  discountReason.value =
    item?.discount?.reason || reasonOptions.value[0]?.ref || "cortesia";
  // Só semeia o campo com o desconto que já existe se ele for do MESMO formato:
  // um "10" de dez por cento aparecendo como dez reais ao trocar de aba é o
  // operador dando um desconto que ele não pediu.
  const vigente =
    item?.discount?.value &&
    (item.discount.type || "percent") === discountKind.value
      ? item.discount.value
      : 0;
  numpadBuffer.value = vigente
    ? discountKind.value === "fixed"
      ? vigente.toFixed(2).replace(".", ",")
      : String(vigente)
    : "";
}

watch(activeLineId, () => syncBufferToMode());
watch(numpadMode, () => syncBufferToMode());

function selectLine(lineId: string) {
  selectedLineId.value = lineId;
  syncBufferToMode();
}

function setMode(mode: "qty" | "disc" | "disc_brl") {
  numpadMode.value = mode;
}

// Observação da linha (Odoo Note): diálogo simples de texto para a linha ativa.
// O dado já existia (POSCartItem.notes, intent, KDS) — só faltava quem editasse.
const noteDialog = ref<{ lineId: string; name: string; text: string } | null>(
  null,
);
function openNoteDialog() {
  const item = activeItem.value;
  if (!item) return;
  noteDialog.value = {
    lineId: item.line_id,
    name: item.name,
    text: item.notes || "",
  };
}
function saveNote() {
  const dialog = noteDialog.value;
  noteDialog.value = null;
  if (!dialog) return;
  emit("setNotes", dialog.lineId, dialog.text.trim());
}

// Remover item PERGUNTA, sempre. Já foi "direto com Desfazer", e o balcão
// discordou: o gesto que mais remove é o backspace zerando a quantidade, e ali
// ninguém teve intenção de excluir — o item sumia e o operador ficava
// procurando um toast que já tinha passado. Um modal custa um toque; recontar o
// pedido do cliente custa a venda.
const confirmAction = ref<
  | { kind: "line"; lineId: string; name: string; fired: boolean }
  | { kind: "batch"; lineIds: string[]; hasFired: boolean }
  | null
>(null);
const confirmTitle = computed(() => {
  const action = confirmAction.value;
  if (!action) return "";
  if (action.kind === "batch") {
    return action.lineIds.length === 1
      ? "Remover o item selecionado?"
      : `Remover ${action.lineIds.length} itens selecionados?`;
  }
  // Item já na cozinha é outra conversa: sair da tela não o tira do fogão.
  return action.fired
    ? "Remover item enviado à cozinha?"
    : `Remover ${action.name}?`;
});
const confirmCta = computed(() =>
  confirmAction.value?.kind === "batch" &&
  confirmAction.value.lineIds.length > 1
    ? "Remover itens"
    : "Remover item",
);
function askRemove(lineId: string) {
  if (props.loading || props.saving) return;
  const item = props.items.find((entry) => entry.line_id === lineId);
  if (!item) return;
  confirmAction.value = {
    kind: "line",
    lineId,
    name: item.name || "item",
    fired: Boolean(item.fired),
  };
}
/** O "Desfazer" continua existindo depois do SIM: confirmar não torna o engano
 *  impossível, só deliberado. */
function removeWithUndo(item: POSCartItem) {
  const snapshot: POSCartItem = { ...item };
  if (selectedLineId.value === item.line_id) selectedLineId.value = "";
  emit("remove", item.line_id);
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
    action.lineIds.forEach((lineId) => emit("remove", lineId));
    clearSelection();
    return;
  }
  const item = props.items.find((entry) => entry.line_id === action.lineId);
  if (item) removeWithUndo(item);
}

function commitQty() {
  if (props.loading || props.saving) return;
  const lineId = activeLineId.value;
  if (!lineId) return;
  const next = clampQty(numpadBuffer.value, MAX_QTY);
  if (next <= 0) {
    askRemove(lineId);
    return;
  }
  emit("setQty", lineId, next);
}

// Discount targets: the whole selection in multi-select, else the active line.
const discountTargets = computed(() =>
  selectMode.value
    ? selection.value.lineIds
    : activeLineId.value
      ? [activeLineId.value]
      : [],
);

// O valor em REAIS que o operador digitou (vírgula → centavos, no máximo duas
// casas). O contrato do desconto fixo fala em reais, igual ao do pedido.
function moneyEntryToReais(entry: string): number {
  const n = Number.parseFloat((entry || "0").replace(",", "."));
  return Number.isFinite(n) && n >= 0
    ? Math.min(999_999, Math.round(n * 100) / 100)
    : 0;
}

function commitDiscount() {
  if (props.loading || props.saving) return;
  const targets = discountTargets.value;
  if (!targets.length) return;
  const value =
    discountKind.value === "fixed"
      ? moneyEntryToReais(numpadBuffer.value)
      : clampPercent(numpadBuffer.value);
  targets.forEach((lineId) =>
    emit(
      "setDiscount",
      lineId,
      value,
      discountReason.value || "cortesia",
      discountKind.value,
    ),
  );
}

// In multi-select the numpad is discount-only (batch quantity is meaningless).
const numpadCanType = computed(() =>
  inDiscountMode.value
    ? discountTargets.value.length > 0
    : !!activeLineId.value,
);
// O que o pad está editando, para os rótulos de leitor de tela acompanharem o modo.

function onDigit(digit: string) {
  if (props.loading || props.saving) return;
  if (!numpadCanType.value) return;
  if (numpadMode.value === "disc_brl") {
    const entry = numpadFresh.value ? "" : numpadBuffer.value;
    if (entry.includes(",")) {
      if ((entry.split(",")[1] ?? "").length >= 2) return;
    } else if (entry.replace(/^0+/, "").length >= 6) {
      return;
    }
    numpadBuffer.value = entry + digit;
    numpadFresh.value = false;
    commitDiscount();
    return;
  }
  numpadBuffer.value = pushDigit(numpadBuffer.value, digit, {
    fresh: numpadFresh.value,
    maxLength: 3,
  });
  numpadFresh.value = false;
  if (numpadMode.value === "qty") commitQty();
  else commitDiscount();
}

// A tecla de vírgula existe só no desconto em R$: o teclado compartilhado é
// inteiro, e centavos precisam de separador.
function onComma() {
  if (props.loading || props.saving) return;
  if (numpadMode.value !== "disc_brl" || !numpadCanType.value) return;
  let entry = numpadFresh.value ? "0" : numpadBuffer.value || "0";
  if (!entry.includes(",")) entry += ",";
  numpadBuffer.value = entry;
  numpadFresh.value = false;
  commitDiscount();
}

function onBackspace() {
  if (props.loading || props.saving) return;
  if (!numpadCanType.value) return;
  if (numpadMode.value === "disc_brl") {
    numpadBuffer.value = (numpadFresh.value ? "" : numpadBuffer.value).slice(
      0,
      -1,
    );
    numpadFresh.value = false;
    commitDiscount();
    return;
  }
  numpadBuffer.value = popDigit(numpadBuffer.value);
  numpadFresh.value = false;
  if (numpadMode.value === "qty") commitQty();
  else commitDiscount();
}

// Entering multi-select switches the numpad to its discount (batch) mode, since
// batch quantity has no meaning; leaving it restores quantity entry.
watch(selectMode, (on) => {
  numpadMode.value = on ? "disc" : "qty";
  numpadBuffer.value = "";
  numpadFresh.value = true;
});

function bump(lineId: string, emitName: "increment" | "decrement") {
  if (props.loading || props.saving) return;
  selectedLineId.value = lineId;
  if (emitName === "decrement") {
    if (qtyOf(lineId) <= 1) {
      askRemove(lineId);
      return;
    }
    emit("decrement", lineId);
    return;
  }
  emit("increment", lineId);
}

// Physical keyboard feeds the active line (Odoo-style): select/add a product,
// then type a number to set its quantity. Ignored while typing in a field — e
// DESLIGADO com o terminal travado ou um diálogo aberto (globalKeysBlocked):
// a página segue montada sob o overlay, e o crachá/PIN digitado ali reescrevia
// quantidades e salvava no servidor.
function onWindowKeydown(event: KeyboardEvent) {
  if (
    globalKeysBlocked() ||
    props.loading ||
    props.saving ||
    event.altKey ||
    event.ctrlKey ||
    event.metaKey ||
    event.defaultPrevented
  )
    return;
  const target = event.target as HTMLElement | null;
  const editing =
    !!target &&
    (target.tagName === "INPUT" ||
      target.tagName === "TEXTAREA" ||
      target.tagName === "SELECT" ||
      target.isContentEditable);
  if (editing || !props.items.length || !activeLineId.value) return;
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
const batchMode = ref(false);
function finishItemMode() {
  batchMode.value = false;
  expandedLineId.value = "";
  clearSelection();
  listEntry.value?.focus();
}
function toggleBatchMode() {
  if (batchMode.value) { finishItemMode(); return; }
  batchMode.value = true;
  expandedLineId.value = "";
  clearSelection();
  void focusItem();
}
function markItem(lineId: string) {
  batchMode.value = true;
  toggleSelect(lineId);
}
const mutationBusy = computed(() => props.loading || props.saving);
const modes = [
  { ref: "qty", label: "Qtd" },
  { ref: "disc", label: "Desc %" },
  { ref: "disc_brl", label: "Desc R$" },
  { ref: "note", label: "Obs." },
] as const;
function chooseMode(mode: (typeof modes)[number]["ref"]) {
  if (mutationBusy.value) return;
  if (mode === "note") openNoteDialog();
  else setMode(mode);
}
const receiptList = ref<HTMLElement | null>(null);
const listEntry = ref<HTMLButtonElement | null>(null);
async function focusItem(lineId = activeLineId.value) {
  const buttons = Array.from(
    receiptList.value?.querySelectorAll<HTMLButtonElement>(
      "[data-item-select]",
    ) || [],
  );
  const button =
    buttons.find((el) => el.dataset.itemSelect === lineId) || buttons[0];
  if (!button) return;
  batchMode.value = true;
  selectLine(button.dataset.itemSelect!);
  await nextTick();
  button.focus({ preventScroll: true });
  button.closest("li")?.scrollIntoView?.({ block: "nearest" });
}
function enterList(event: KeyboardEvent) {
  if (
    event.altKey &&
    !event.ctrlKey &&
    !event.metaKey &&
    (event.code === "KeyS" || event.key.toLowerCase() === "s") &&
    !globalKeysBlocked() &&
    !props.loading &&
    !props.saving &&
    !(props.requiresTab && !props.hasOpenTab)
  ) {
    event.preventDefault();
    focusItem();
  }
}
onMounted(() => window.addEventListener("keydown", enterList));
onBeforeUnmount(() => window.removeEventListener("keydown", enterList));
async function navigateItems(event: KeyboardEvent) {
  if (
    event.altKey ||
    event.ctrlKey ||
    event.metaKey ||
    event.shiftKey ||
    globalKeysBlocked() ||
    props.loading ||
    props.saving
  )
    return;
  const target = event.target as HTMLElement;
  if (
    target.closest(
      'input, textarea, select, [contenteditable="true"], [role="dialog"]',
    )
  )
    return;
  const row = target.closest("li");
  const primary = row?.querySelector<HTMLButtonElement>("[data-item-select]");
  if (!primary) return;
  const id = primary.dataset.itemSelect!;
  const buttons = Array.from(
    receiptList.value?.querySelectorAll<HTMLButtonElement>(
      "[data-item-select]",
    ) || [],
  );
  const index = buttons.indexOf(primary);
  if (
    event.key === " " &&
    target === primary
  ) {
    event.preventDefault();
    event.stopPropagation();
    markItem(id);
  } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
    event.preventDefault();
    event.stopPropagation();
    const next =
      buttons[
        Math.max(
          0,
          Math.min(
            buttons.length - 1,
            index + (event.key === "ArrowDown" ? 1 : -1),
          ),
        )
      ];
    if (next) await focusItem(next.dataset.itemSelect!);
  } else if (
    (event.key === "ArrowRight" ||
      event.key === "ArrowLeft" ||
      (event.key === "Enter" && target === primary))
  ) {
    event.preventDefault();
    event.stopPropagation();
    selectLine(id);
    expandedLineId.value =
      event.key === "ArrowRight"
        ? id
        : event.key === "ArrowLeft"
          ? ""
          : expandedLineId.value === id
            ? ""
            : id;
  } else if (!selectMode.value && ["+", "-", "Delete"].includes(event.key)) {
    event.preventDefault();
    event.stopPropagation();
    if (event.key === "Delete") askRemove(id);
    else bump(id, event.key === "+" ? "increment" : "decrement");
  } else if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    if (expandedLineId.value) expandedLineId.value = "";
    else finishItemMode();
  }
}
defineExpose({ focusItem, onDigit, onBackspace });
</script>

<template>
  <UiCard
    v-if="requiresTab && !hasOpenTab"
    class="gap-4 rounded-md p-4 shadow-none md:h-full md:min-h-0"
  >
    <div class="grid gap-3 text-center">
      <div
        class="mx-auto grid size-11 place-items-center rounded-md border bg-muted"
      >
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

  <div
    v-else
    class="flex min-h-0 flex-col overflow-hidden bg-card text-card-foreground md:h-full"
  >
    <header
      class="flex min-h-[var(--pos-context-header-height,53px)] shrink-0 items-center justify-between gap-2 border-b px-3 py-1.5"
    >
      <div class="flex items-center gap-2">
        <h3 class="whitespace-nowrap text-base font-semibold">{{ items.length }} {{ items.length === 1 ? "item" : "itens" }}</h3>
      </div>
      <button
        ref="listEntry"
        aria-keyshortcuts="Alt+s"
        title="Alt+S: selecionar itens"
        class="inline-flex h-9 shrink-0 items-center gap-2 rounded-full border border-border px-3 text-sm font-medium transition hover:bg-accent"
        :aria-label="batchMode ? 'Concluir seleção' : 'Iniciar seleção'"
        @click="toggleBatchMode"
      >
        {{ batchMode ? "Concluir seleção" : "Selecionar" }}
        <OperatorKbd v-if="!batchMode" aria-hidden="true">Alt S</OperatorKbd>
      </button>
    </header>
    <div
      ref="receiptList"
      class="min-h-0 flex-1 overflow-y-auto"
      data-receipt-list
      @keydown="navigateItems"
    >
      <p
        v-if="!items.length"
        class="p-6 text-center text-sm text-muted-foreground"
      >
        Escolha um produto para começar.
      </p>
      <ul class="divide-y divide-border/40">
        <li
          v-for="item in items"
          :key="item.line_id"
          class="relative flex flex-wrap items-start border-l"
          :aria-current="activeLineId === item.line_id ? 'true' : undefined"
          :class="
            isSelected(item.line_id)
              ? 'border-l-primary bg-primary/10'
              : activeLineId === item.line_id
                ? 'border-l-primary bg-primary/5'
                : 'border-l-transparent hover:bg-muted/50'
          "
          @click="batchMode && toggleSelect(item.line_id)"
        >
          <button
            v-if="batchMode"
            class="grid size-11 shrink-0 place-items-center"
            :aria-label="`Selecionar ${item.name}`"
            :aria-pressed="isSelected(item.line_id)"
            @click.stop="toggleSelect(item.line_id)"
          >
            <span
              class="grid size-4 place-items-center rounded border"
              :class="
                isSelected(item.line_id)
                  ? 'bg-primary text-primary-foreground'
                  : ''
              "
              ><Icon
                v-if="isSelected(item.line_id)"
                name="lucide:check"
                class="size-3"
            /></span>
          </button>
          <button
            class="grid min-h-11 min-w-0 flex-1 grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-x-2 pl-3 pr-1 pt-2 text-left focus-visible:outline-none"
            :class="activeLineId === item.line_id && !batchMode ? 'pb-1' : 'pb-2'"
            :data-item-select="item.line_id"
            :aria-label="`Editar ${item.name}`"
            :aria-pressed="
              batchMode
                ? isSelected(item.line_id)
                : activeLineId === item.line_id
            "
            :aria-expanded="expandedLineId === item.line_id"
            :aria-controls="detailsId(item.line_id)"
            @focus="selectLine(item.line_id)"
            @click="selectLine(item.line_id)"
          >
            <span class="py-0.5 text-sm font-semibold tabular-nums"
              >{{ item.qty }}
              <span class="font-normal text-muted-foreground">×</span></span
            >
            <span
              class="min-w-0 py-0.5 text-sm font-medium leading-snug [overflow-wrap:anywhere]"
              >{{ item.name }}</span
            >
            <strong class="py-0.5 text-sm font-semibold tabular-nums">{{
              formatBRL(lineTotalQ(item))
            }}</strong>
            <span
              class="col-start-2 col-end-4 text-xs leading-4 text-muted-foreground"
              >{{ formatBRL(unitChargedQ(item)) }} cada</span
            >
            <span
              v-if="item.notes"
              class="col-start-2 col-end-4 mt-1 text-xs leading-relaxed text-muted-foreground"
              >{{ item.notes }}</span
            >
            <span
              v-if="discountBadge(item) || lineKitchenState(item) !== 'unfired'"
              class="col-start-2 col-end-4 flex flex-wrap gap-2 text-xs text-muted-foreground"
              ><span
                v-if="discountBadge(item)"
                class="text-primary"
                :title="discountBadge(item)"
                >{{ compactDiscount(item) }}</span
              ><span
                v-if="lineKitchenState(item) !== 'unfired'"
                :class="badgeTone(kitchenBadge(item).tone)"
                >{{ kitchenBadge(item).label }}</span
              ></span
            >
          </button>
          <button
            class="grid min-h-11 w-9 shrink-0 place-items-center text-muted-foreground"
            :aria-label="`Detalhes de ${item.name}`"
            :aria-expanded="expandedLineId === item.line_id"
            :aria-controls="detailsId(item.line_id)"
            @click.stop="toggleDetails(item.line_id)"
          >
            <Icon
              :name="
                expandedLineId === item.line_id
                  ? 'lucide:chevron-up'
                  : 'lucide:chevron-down'
              "
              class="size-4"
            />
          </button>
          <div
            v-if="activeLineId === item.line_id && !batchMode"
            class="flex w-full items-center justify-between gap-2 px-3 pb-2"
            aria-label="Ajustes do item"
          >
            <div
              class="inline-flex items-center overflow-hidden rounded-md border border-primary/20 bg-card"
              role="group"
              :aria-label="`Quantidade de ${item.name}`"
            >
              <button
                class="grid size-9 place-items-center text-lg hover:bg-primary/10 focus-visible:bg-primary/10"
                aria-label="Diminuir"
                :disabled="mutationBusy"
                @click="bump(item.line_id, 'decrement')"
              >
                −
              </button>
              <button
                type="button"
                class="min-h-9 min-w-8 border-x border-primary/10 text-center text-sm font-semibold tabular-nums"
                :aria-label="`Editar quantidade de ${item.name}`"
                :disabled="mutationBusy"
                @click="
                  selectLine(item.line_id);
                  setMode('qty');
                "
              >
                {{ item.qty }}
              </button>
              <button
                class="grid size-9 place-items-center text-lg hover:bg-primary/10 focus-visible:bg-primary/10"
                aria-label="Aumentar"
                :disabled="mutationBusy"
                @click="bump(item.line_id, 'increment')"
              >
                +
              </button>
            </div>
            <button
              class="inline-flex min-h-9 items-center gap-1.5 rounded-md px-2 text-xs text-destructive hover:bg-destructive/10 focus-visible:bg-destructive/10"
              aria-label="Remover"
              :disabled="mutationBusy"
              @click="askRemove(item.line_id)"
            >
              <Icon name="lucide:trash-2" class="size-3.5" />Remover
            </button>
          </div>
          <div
            v-if="expandedLineId === item.line_id"
            :id="detailsId(item.line_id)"
            role="region"
            :aria-label="`Detalhes de ${item.name}`"
            class="w-full px-3 pb-2 text-xs leading-relaxed"
          >
            <p v-if="discountBadge(item)" class="mt-1">
              {{ discountBadge(item) }}
            </p>
            <p v-if="lineListTotalDisplay(item)" class="text-muted-foreground">
              De
              <span class="line-through" :title="discountBadge(item)">{{
                lineListTotalDisplay(item)
              }}</span>
              por {{ formatBRL(lineTotalQ(item)) }}
            </p>
            <div v-if="item.authorship" class="text-muted-foreground">
              <p v-if="item.authorship.created_by">
                Lançado por
                {{
                  item.authorship.created_label || item.authorship.created_by
                }}
              </p>
              <p v-if="item.authorship.updated_by">
                Editado por
                {{
                  item.authorship.updated_label || item.authorship.updated_by
                }}
              </p>
            </div>
            <ClientOnly
              ><p
                v-if="item.authorship?.updated_at"
                class="text-muted-foreground"
              >
                {{
                  new Date(item.authorship.updated_at).toLocaleString("pt-BR", {
                    day: "2-digit",
                    month: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                }}
              </p></ClientOnly
            ><UiButton
              v-if="lineKitchenState(item) === 'fired_cancellable'"
              variant="ghost"
              size="sm"
              :disabled="mutationBusy || firing || !unfireAction.enabled"
              @click.stop="$emit('unfire', item.line_id)"
              >{{ unfireAction.label }}</UiButton
            >
            <div v-if="!batchMode" class="mt-1 flex justify-between">
              <button
                class="min-h-9 font-medium text-primary"
                @click="
                  selectLine(item.line_id);
                  openNoteDialog();
                "
              >
                <Icon
                  name="lucide:sticky-note"
                  class="mr-1 inline size-4"
                />Observação
              </button>
            </div>
          </div>
        </li>
      </ul>
    </div>
    <div v-if="selectMode" class="shrink-0 border-t bg-primary/5 p-3">
      <div class="mb-2 flex items-center justify-between">
        <span class="text-sm font-semibold"
          >{{ selection.count }}
          {{
            selection.count === 1 ? "item selecionado" : "itens selecionados"
          }}</span
        ><button
          class="min-h-9 px-2 text-xs text-muted-foreground"
          aria-label="Limpar seleção"
          @click="clearSelection"
        >
          Limpar
        </button>
      </div>
      <div class="grid grid-cols-2 gap-2">
        <UiButton
          v-if="fireAction.present"
          variant="outline"
          class="gap-1.5 bg-card text-primary"
          :disabled="
            mutationBusy || firing || !selection.canFire || !fireAction.enabled
          "
          @click="batchFire"
          ><Icon name="lucide:utensils" class="size-4" />{{
            fireAction.label || "Enviar"
          }}</UiButton
        ><UiButton
          variant="outline"
          class="gap-1.5 border-destructive/25 bg-card text-destructive hover:bg-destructive/10"
          :disabled="mutationBusy"
          @click="batchRemove"
          ><Icon name="lucide:trash-2" class="size-4" />Remover</UiButton
        >
      </div>
      <UiButton
        v-if="selection.canUnfire && unfireAction.present"
        :disabled="mutationBusy || firing || !unfireAction.enabled"
        variant="ghost"
        class="mt-1 w-full gap-1.5 text-xs"
        @click="batchUnfire"
        ><Icon name="lucide:undo-2" class="size-3.5" />{{
          unfireAction.label || "Cancelar envio"
        }}</UiButton
      >
    </div>
    <section
      v-if="activeItem"
      class="shrink-0 border-t bg-card p-2"
      aria-label="Console do item"
    >
      <div class="grid grid-cols-[minmax(0,1fr)_70px] gap-2">
        <div class="grid grid-cols-3 gap-1">
          <button
            v-for="key in [1, 2, 3, 4, 5, 6, 7, 8, 9, 'decimal', 0, 'back']"
            :key="key"
            class="h-11 rounded-md border bg-card text-base font-semibold hover:bg-muted"
            :class="
              key === 'back' ? 'border-destructive/30 text-destructive' : ''
            "
            :aria-label="
              typeof key === 'number'
                ? 'Dígito ' + key
                : key === 'back'
                  ? 'Apagar último dígito'
                  : 'Vírgula'
            "
            :disabled="
              mutationBusy ||
              !numpadCanType ||
              (key === 'decimal' && numpadMode !== 'disc_brl')
            "
            @click="
              typeof key === 'number'
                ? onDigit(String(key))
                : key === 'back'
                  ? onBackspace()
                  : onComma()
            "
          >
            {{ typeof key === "number" ? key : key === "back" ? "⌫" : "," }}
          </button>
        </div>
        <div class="grid grid-rows-4 gap-1">
          <button
            v-for="mode in modes"
            :key="mode.ref"
            class="h-11 rounded-md border text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-35 disabled:saturate-0"
            :class="
              numpadMode === mode.ref
                ? 'border-primary bg-primary text-primary-foreground'
                : 'bg-card text-primary'
            "
            :aria-pressed="numpadMode === mode.ref"
            :disabled="
              mutationBusy ||
              (selectMode && (mode.ref === 'qty' || mode.ref === 'note'))
            "
            @click="chooseMode(mode.ref)"
          >
            {{ mode.label }}
          </button>
        </div>
      </div>
      <div v-if="inDiscountMode" class="mt-2">
        <p class="mb-1 text-xs text-muted-foreground">
          {{
            selectMode
              ? `Desconto em ${selection.count} itens`
              : numpadMode === "disc_brl"
                ? "Desconto por unidade"
                : "Desconto percentual"
          }}:
          <strong>{{
            numpadMode === "disc_brl"
              ? `R$ ${numpadBuffer || "0"}`
              : `${numpadBuffer || "0"}%`
          }}</strong>
        </p>
        <select
          v-model="discountReason"
          aria-label="Motivo do desconto"
          :disabled="mutationBusy"
          class="h-11 w-full rounded-md border bg-card px-2 text-xs"
          @change="commitDiscount"
        >
          <option
            v-for="reason in reasonOptions"
            :key="reason.ref"
            :value="reason.ref"
          >
            {{ reason.label }}
          </option>
        </select>
      </div>
    </section>
    <div class="grid shrink-0 gap-2 border-t px-3 py-2">
      <div class="flex items-baseline justify-between">
        <span class="text-sm font-medium text-muted-foreground"
          >Total parcial</span
        >
        <strong class="text-xl font-semibold tabular-nums">{{
          totalDisplay
        }}</strong>
      </div>
      <!-- Secondary actions stack on the left; Pagamento is the highlight column
           spanning their full height — saves a vertical row. -->
      <div
        v-if="!batchMode && (fireBar.visible || (hasOpenTab && items.length))"
        class="grid grid-cols-2 gap-2"
      >
        <div class="flex flex-col gap-2">
          <!-- ENVIAR ganha calor quando HÁ o que enviar: item lançado e não
               enviado é trabalho parado, e o botão neutro dizia isso com a
               mesma voz de um botão desligado. Emprestamos o idioma de ênfase
               da casa (borda + fundo primário) em vez de um segundo botão
               sólido: o sólido é do "Pagamento", e dois blocos cheios lado a
               lado brigam pela mesma atenção em vez de dirigi-la. A contagem
               virou badge — o número é o dado, o resto é rótulo. -->
          <UiButton
            v-if="fireBar.visible"
            variant="outline"
            class="justify-center gap-2"
            :class="
              fireBar.unfired && !fireBar.disabled
                ? 'border-primary bg-primary/5 text-primary hover:bg-primary/10'
                : ''
            "
            :disabled="fireBar.disabled"
            :loading="firing"
            @click="$emit('fire')"
          >
            <Icon name="lucide:utensils" class="size-4" />
            {{ fireBar.label }}
            <span
              v-if="fireBar.unfired"
              class="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-primary px-1.5 text-xs font-semibold tabular-nums text-primary-foreground"
              :aria-label="`${fireBar.unfired} item(ns) a enviar`"
              >{{ fireBar.unfired }}</span
            >
          </UiButton>
          <UiButton
            v-if="hasOpenTab && items.length"
            variant="outline"
            class="justify-center gap-1.5"
            :disabled="loading"
            @click="$emit('move')"
          >
            <Icon name="lucide:split" class="size-4" />
            Transferir
          </UiButton>
        </div>
        <UiButton
          size="lg"
          class="h-full flex-col gap-1 text-base"
          :disabled="!items.length || loading || saving"
          :loading="loading"
          @click="$emit('prepare')"
        >
          <Icon name="lucide:credit-card" class="size-6" />
          Pagamento
          <OperatorKbd variant="inverse" aria-hidden="true">F4</OperatorKbd>
        </UiButton>
      </div>
      <UiButton
        v-else-if="!batchMode"
        size="lg"
        class="w-full gap-2"
        :disabled="!items.length || loading || saving"
        :loading="loading"
        @click="$emit('prepare')"
      >
        <Icon name="lucide:credit-card" class="size-5" />
        Pagamento
        <OperatorKbd variant="inverse" aria-hidden="true">F4</OperatorKbd>
      </UiButton>
    </div>
  </div>

  <UiDialog
    :open="!!noteDialog"
    @update:open="
      (value) => {
        if (!value) noteDialog = null;
      }
    "
  >
    <UiDialogContent class="sm:max-w-sm">
      <UiDialogHeader>
        <UiDialogTitle>Observação · {{ noteDialog?.name }}</UiDialogTitle>
        <UiDialogDescription
          >A observação sai junto com o item para a
          cozinha.</UiDialogDescription
        >
      </UiDialogHeader>
      <UiTextarea
        v-if="noteDialog"
        v-model="noteDialog.text"
        :rows="3"
        placeholder="Ex: sem cebola, bem passado"
        autofocus
      />
      <UiDialogFooter class="gap-2">
        <UiButton variant="outline" @click="noteDialog = null"
          >Cancelar</UiButton
        >
        <UiButton @click="saveNote">Salvar observação</UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>

  <UiDialog
    :open="!!confirmAction"
    @update:open="
      (value) => {
        if (!value) cancelConfirm();
      }
    "
  >
    <UiDialogContent class="sm:max-w-sm">
      <UiDialogHeader>
        <UiDialogTitle>{{ confirmTitle }}</UiDialogTitle>
        <UiDialogDescription
          v-if="confirmAction?.kind === 'line' && confirmAction.fired"
        >
          <strong>{{ confirmAction.name }}</strong> já foi enviado à cozinha.
          Remover tira a linha do pedido; avise o preparo se necessário.
        </UiDialogDescription>
        <UiDialogDescription v-else-if="confirmAction?.kind === 'line'">
          A linha sai do pedido. Dá para desfazer logo depois.
        </UiDialogDescription>
        <UiDialogDescription v-else-if="confirmAction?.kind === 'batch'">
          {{
            confirmAction.hasFired
              ? "As linhas selecionadas saem do pedido, inclusive as que já foram à cozinha."
              : "As linhas selecionadas saem do pedido."
          }}
        </UiDialogDescription>
      </UiDialogHeader>
      <UiDialogFooter class="gap-2">
        <UiButton variant="outline" @click="cancelConfirm">Cancelar</UiButton>
        <UiButton variant="destructive" @click="runConfirm">{{
          confirmCta
        }}</UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
