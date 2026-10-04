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
  countUnits,
  pruneSelection,
  selectionView,
  toggleSelected,
} from "~/presentation/selection";
import {
  lineDiscountBadge,
  lineListUnitQ,
  lineListTotalDisplay,
  lineTotalQ,
  unitChargedQ,
} from "~/presentation/lineDiscounts";
import { cartNetTotalQ } from "~/presentation/receipt";
import { isWeighedLine, lineQtyLabel } from "~/presentation/weighed";
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
  /**
   * O gesto principal do carrinho. Na venda é "Pagamento"; na edição de uma
   * encomenda (a mesma tela, em modo edição) é "Salvar alterações" — o carrinho
   * não cobra, grava a encomenda.
   */
  primaryLabel?: string;
  primaryIcon?: string;
  /**
   * Esconde "Transferir" linhas entre comandas: não existe na edição de
   * encomenda. (Negativo de propósito: prop booleana ausente vira `false`.)
   */
  hideMove?: boolean;
  /**
   * Quando presente, desconto e observação de ITEM ficam fora da tela, e esta é
   * a frase que diz por quê. Na edição de encomenda o serviço não os grava:
   * mostrar o gesto seria deixar o operador fazer algo que some ao salvar.
   */
  lineAdjustmentsBlockedReason?: string;
  /**
   * A comanda é a FOLHA de baixo (tablet e celular, v4 `pos-tablet.jpg`): fechada,
   * resumo e Pagamento; aberta, as linhas e o editor. No desktop ela é a coluna.
   */
  sheet?: boolean;
  /**
   * Para onde cada produto vai na cozinha (sku → estação), lido do roteamento
   * real (`kitchen_station` do catálogo). A linha nova com preparo diz "vai à
   * cozinha" ANTES do envio (v4); sem estação, a linha não carrega fato nenhum.
   */
  kitchenStations?: Record<string, string>;
  /** O nome da comanda ("Mesa 6"), que a folha aberta lê no cabeçalho ("Mesa 6 · 4 itens"). */
  tabTitle?: string;
  /** Alguma linha desta comanda é de estação com envio automático ligado. */
  autoFire?: boolean;
  /**
   * Os meios eletrônicos que a folha oferece direto (v4 tablet, `pos-tablet.jpg`
   * b): PIX e Maquininha. Vazio, a folha mostra só o Pagamento de sempre.
   */
  quickPayments?: Array<{ ref: string; label: string; icon: string }>;
}>();
const sheetOpen = ref(false);
const lineAdjustmentsBlocked = computed(() => Boolean(props.lineAdjustmentsBlockedReason));
const primaryText = computed(() => props.primaryLabel || "Pagamento");
const primaryIconName = computed(() => props.primaryIcon || "lucide:credit-card");
const canMove = computed(() => !props.hideMove);

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
  /** Transferir: no modo seleção leva as linhas marcadas (o diálogo nasce com elas). */
  move: [lineIds?: string[]];
  fire: [];
  unfire: [string];
  /** Multi-select batch (spec §2.2): fire/unfire exatamente estas linhas. */
  fireLines: [string[], (success: boolean) => void];
  unfireLines: [string[], (success: boolean) => void];
  requestTab: [];
  /** Pagar direto na folha por um meio (PIX, Maquininha): abre o Pagamento já nele. */
  pay: [method: string];
  /** O interruptor do envio automático mora por estação, em Ajustes › Envio à cozinha. */
  autoFireSettings: [];
}>();

// Multi-select (spec §2.2): selection is screen state (um conjunto de
// `line_id`s); the batch toolbar is shaped purely (presentation/selection).
// Tapping a line's checkbox toggles it without arming the numpad; the toolbar
// acts on all chosen.
const selected = ref<Set<string>>(new Set());
const selection = computed(() => selectionView(props.items, selected.value));
// O cabeçalho da comanda conta ITENS, não linhas — a mesma grandeza da cozinha,
// do resumo do pagamento, do quadro de comandas e da tela virada para o
// cliente. Era o último lugar do app que ainda falava linha, e o mais lido.
const cartUnits = computed(() => countUnits(props.items));
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
  confirmAction.value = { kind: "batch", lineIds, units: selection.value.units, hasFired };
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
    return "bg-warning/10 text-warning";
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

// O card da cozinha da linha: estação, itens, disparo, estado — e o "Pronto" da
// estação sem tela. Guarda o line_id (não a linha): o push da cozinha troca o
// array de itens, e o diálogo aberto acompanha o estado novo.
const kitchenLineId = ref("");
const kitchenLine = computed(() => props.items.find((item) => item.line_id === kitchenLineId.value) ?? null);
function hasKitchenCard(item: POSCartItem): boolean {
  return Boolean(item.fired && item.kitchen_tickets?.length);
}
const detailsPrefix = useId();
function detailsId(lineId: string) {
  return `${detailsPrefix}-${encodeURIComponent(lineId)}`;
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

// "Quantidade de Cappuccino (era 1)" (v4 tablet): o número de quando o editor
// abriu a linha, para o operador conferir o que mudou.
const qtyWas = ref(0);
function selectLine(lineId: string) {
  if (lineId !== selectedLineId.value || editorClosed.value) qtyWas.value = qtyOf(lineId);
  selectedLineId.value = lineId;
  editorClosed.value = false;
  syncBufferToMode();
}
/** A linha vai à cozinha quando for enviada (há estação para o produto dela). */
function goesToKitchen(item: POSCartItem): boolean {
  return !item.fired && Boolean(props.kitchenStations?.[item.sku]);
}
// Com itens a enviar, a folha fechada promove "Enviar à cozinha" a primária e o
// Pagamento fica ao lado, contornado (v4 `pos-tablet-fluxo` 1).
const sheetFirePrimary = computed(() => Boolean(props.sheet && fireBar.value.visible && fireBar.value.unfired && !fireBar.value.disabled));

// ── Editor da linha, sob demanda (v4) ─────────────────────────────────────────
// Aberto para a linha ativa (a tocada, ou a última lançada); "Fechar" (Esc) devolve
// a lista inteira até a próxima linha tocada, o próximo produto lançado ou o próximo
// dígito do teclado físico (o teclado continua editando a linha ativa, como sempre).
// No toque (tablet, prévia `pos-tablet.jpg`) o editor e o numérico só aparecem ao
// tocar a linha: a lista fica inteira enquanto se lança.
const coarsePointer = useMediaQuery("(pointer: coarse)");
const editorClosed = ref(false);
onMounted(() => { if (coarsePointer.value) editorClosed.value = true; });
const editorVisible = computed(() => Boolean(activeItem.value) && !batchMode.value && !editorClosed.value);
function closeEditor() {
  editorClosed.value = true;
  discountOpen.value = false;
  if (inDiscountMode.value) numpadMode.value = "qty";
}
watch(
  () => props.items.length,
  (length, previous) => {
    if (length > (previous ?? 0) && !coarsePointer.value) editorClosed.value = false;
  },
);

// O desconto abre no mesmo lugar do editor: formato (% ou R$), valor e motivo. Na
// seleção, vale para as linhas marcadas.
const discountOpen = ref(false);
const discountModes = [
  { ref: "disc", label: "Em %" },
  { ref: "disc_brl", label: "Em R$" },
] as const;
function toggleDiscount() {
  if (mutationBusy.value || lineAdjustmentsBlocked.value) return;
  discountOpen.value = !discountOpen.value;
  if (discountOpen.value && !inDiscountMode.value) setMode(activeItem.value?.discount?.type === "fixed" ? "disc_brl" : "disc");
  if (!discountOpen.value && !selectMode.value) setMode("qty");
}
const discountButtonLabel = computed(() => {
  const discount = activeItem.value?.discount;
  if (!discount?.value) return "Desconto";
  return discount.type === "fixed"
    ? `Desconto: ${formatBRL(Math.round(discount.value * 100))}`
    : `Desconto: ${String(discount.value).replace(".", ",")}%`;
});

// O numérico da tela: no desconto (valor com vírgula) e, nos dispositivos de toque
// (tablet, sem teclado físico), também para a quantidade. No balcão com teclado, a
// quantidade se digita direto (a dica fica no pé da lista).
const numpadVisible = computed(() => {
  if (batchMode.value) return discountOpen.value && !lineAdjustmentsBlocked.value;
  if (!editorVisible.value) return false;
  // No toque o numérico mora DENTRO do editor (um instrumento só, v4 tablet b).
  if (touchEditor.value) return false;
  return discountOpen.value;
});
/** O editor de toque (v4 `pos-tablet.jpg` b): "Quantidade de X (era 1)", a caixa
 *  grande, o numérico 3×4 de 64 px e a coluna Desconto · Observação · Remover ·
 *  Pronto. Um instrumento só para a quantidade, sem −/+ duplicado. */
const touchEditor = computed(() => coarsePointer.value && editorVisible.value && !batchMode.value);
/** O que a caixa grande mostra: a quantidade, ou o desconto que se digita. */
const touchEditorValue = computed(() => {
  const item = activeItem.value;
  if (!item) return "";
  if (inDiscountMode.value) return numpadMode.value === "disc_brl" ? `R$ ${numpadBuffer.value || "0"}` : `${numpadBuffer.value || "0"}%`;
  return isWeighedLine(item) ? lineQtyLabel(item) : String(item.qty);
});
/** Quem lançou e quem editou a linha ativa, numa frase (era o "⌄" da linha). */
const activeAuthorship = computed(() => {
  const a = activeItem.value?.authorship;
  if (!a) return "";
  const parts = [];
  if (a.created_by) parts.push(`Lançado por ${a.created_label || a.created_by}`);
  if (a.updated_by) parts.push(`editado por ${a.updated_label || a.updated_by}`);
  return parts.join(", ");
});

/** "Na cozinha 21:52": o selo da cozinha com a hora do envio, quando ela existe. */
function kitchenFact(item: POSCartItem): string {
  const badge = kitchenBadge(item);
  const firedAt = item.kitchen_tickets?.[0]?.fired_at_display || "";
  return badge.label === "Na cozinha" && firedAt ? `${badge.label} ${firedAt}` : badge.label;
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
  if (lineAdjustmentsBlocked.value) return;
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
  | { kind: "batch"; lineIds: string[]; units: number; hasFired: boolean }
  | null
>(null);
const confirmTitle = computed(() => {
  const action = confirmAction.value;
  if (!action) return "";
  if (action.kind === "batch") {
    // ITENS, não linhas: o que sai do pedido são os três croissants, não "1".
    return action.units === 1
      ? "Remover o item selecionado?"
      : `Remover ${action.units} itens selecionados?`;
  }
  // Item já na cozinha é outra conversa: sair da tela não o tira do fogão.
  return action.fired
    ? "Remover item enviado à cozinha?"
    : `Remover ${action.name}?`;
});
const confirmCta = computed(() =>
  confirmAction.value?.kind === "batch" && confirmAction.value.units > 1
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
  if (props.loading || props.saving || lineAdjustmentsBlocked.value) return;
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
// A peça pesada não tem quantidade digitável: o peso veio da etiqueta, e "2"
// no teclado viraria 2 kg. Trocar a peça é remover e lançar a outra etiqueta.
// E o desconto em R$ é POR UNIDADE — na peça pesada seria "por quilo", que
// ninguém no balcão quer dizer; nela, desconto é em %.
const numpadCanType = computed(() => {
  // Sem desconto de item, a seleção múltipla não tem o que digitar.
  if (lineAdjustmentsBlocked.value && (selectMode.value || inDiscountMode.value)) return false;
  const weighedActive = !!activeItem.value && isWeighedLine(activeItem.value);
  if (!inDiscountMode.value) return !!activeLineId.value && !weighedActive;
  if (numpadMode.value === "disc_brl" && !selectMode.value && weighedActive) return false;
  return discountTargets.value.length > 0;
});
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
  numpadMode.value = on && !lineAdjustmentsBlocked.value ? "disc" : "qty";
  numpadBuffer.value = "";
  numpadFresh.value = true;
});

function bump(lineId: string, emitName: "increment" | "decrement") {
  if (props.loading || props.saving) return;
  const line = props.items.find((entry) => entry.line_id === lineId);
  if (line && isWeighedLine(line)) return;
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
    revealForKeyboard();
    onDigit(event.key);
  } else if (event.key === "Backspace") {
    event.preventDefault();
    revealForKeyboard();
    onBackspace();
  } else if (!batchMode.value && editorVisible.value && event.key === "Escape") {
    // v4: "Fechar · Esc". Fora de campo, o Esc da venda não tinha outro dono.
    event.preventDefault();
    closeEditor();
  } else if (!batchMode.value && event.key === "Delete") {
    // v4: "Del remove" a linha ativa (sempre com a confirmação).
    event.preventDefault();
    askRemove(activeLineId.value);
  } else if (!batchMode.value && editorVisible.value && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
    // v4: "↑↓ troca a linha" com o editor aberto.
    event.preventDefault();
    const index = props.items.findIndex((entry) => entry.line_id === activeLineId.value);
    const next = props.items[Math.max(0, Math.min(props.items.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)))];
    if (next) selectLine(next.line_id);
  }
}
/** O teclado físico digitou: o editor (ou o desconto do lote) volta à vista. */
function revealForKeyboard() {
  if (batchMode.value) {
    if (selectMode.value && !lineAdjustmentsBlocked.value) discountOpen.value = true;
    return;
  }
  editorClosed.value = false;
}
onMounted(() => window.addEventListener("keydown", onWindowKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onWindowKeydown));
const batchMode = ref(false);
function finishItemMode() {
  batchMode.value = false;
  discountOpen.value = false;
  expandedLineId.value = "";
  clearSelection();
  listEntry.value?.focus();
}
function toggleBatchMode() {
  if (batchMode.value) { finishItemMode(); return; }
  batchMode.value = true;
  discountOpen.value = false;
  expandedLineId.value = "";
  clearSelection();
  void focusItem();
}
function markItem(lineId: string) {
  batchMode.value = true;
  toggleSelect(lineId);
}
const mutationBusy = computed(() => props.loading || props.saving);
/** O que o editor da linha escolhe: quantidade, desconto (% ou R$) ou observação. */
type LineMode = "qty" | "disc" | "disc_brl" | "note";
function chooseMode(mode: LineMode) {
  if (mutationBusy.value) return;
  if (lineAdjustmentsBlocked.value && mode !== "qty") return;
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
    else if (batchMode.value) finishItemMode();
    else closeEditor();
  }
}
defineExpose({ focusItem, onDigit, onBackspace });
</script>

<template>
  <div
    v-if="requiresTab && !hasOpenTab"
    class="grid content-center gap-4 bg-card p-6 text-center md:h-full md:min-h-0"
  >
    <div class="mx-auto grid size-12 place-items-center rounded-full bg-secondary">
      <Icon name="lucide:receipt-text" class="size-6 text-muted-foreground" />
    </div>
    <div class="grid gap-1">
      <p class="op-title">Abra uma comanda</p>
      <p class="op-body text-muted-foreground">
        Escolha uma comanda para este atendimento não se perder.
      </p>
    </div>
    <UiButton type="button" size="lg" :disabled="loading" @click="$emit('requestTab')">
      Escolher comanda
    </UiButton>
  </div>

  <!-- COMPOSIÇÃO (v4, `pos-sale4.html`): a comanda é lista + total + Pagamento, e só.
       O editor da linha aparece sob demanda, colado no pé da lista; o numérico da
       tela só no desconto e nos dispositivos de toque (no balcão o teclado físico
       digita a quantidade). -->
  <div
    v-else
    class="relative flex min-h-0 flex-col bg-card text-card-foreground"
    :class="sheet ? 'max-h-[82dvh] rounded-t-2xl border-t border-border shadow-[0_-12px_30px_rgb(0_0_0/.16)]' : 'overflow-hidden md:h-full'"
    :data-pos-sheet="sheet ? (sheetOpen ? 'open' : 'closed') : undefined"
    data-pos-ticket
  >
    <!-- FOLHA (v4 tablet, `pos-tablet.jpg`): abaixo do desktop a comanda é a folha de
         baixo. Fechada, mostra o resumo e o Pagamento na zona do polegar; puxada, as
         linhas, o editor e o numérico (só ao tocar a linha). -->
    <template v-if="sheet">
      <div v-if="sheetOpen" class="fixed inset-0 -z-10 bg-black/35" aria-hidden="true" data-pos-sheet-backdrop @click="sheetOpen = false" />
      <button
        type="button"
        class="mx-auto grid h-5 w-20 shrink-0 place-items-center"
        :aria-label="sheetOpen ? 'Recolher a comanda' : 'Abrir a comanda'"
        :aria-expanded="sheetOpen"
        data-pos-sheet-handle
        @click="sheetOpen = !sheetOpen"
      >
        <span class="h-1.5 w-12 rounded-full bg-border" aria-hidden="true" />
      </button>
      <div v-if="!sheetOpen" class="grid gap-2 px-4 pt-1 pb-3" :class="sheetFirePrimary ? '' : 'sm:flex sm:items-center sm:gap-3'">
      <button
        type="button"
        class="flex min-h-14 min-w-0 flex-1 items-center gap-3 text-left"
        aria-label="Abrir a comanda"
        data-pos-sheet-summary
        @click="sheetOpen = true"
      >
        <span class="relative grid size-11 shrink-0 place-items-center rounded-lg bg-secondary">
          <Icon name="lucide:receipt-text" class="size-5" />
          <span v-if="cartUnits" class="absolute -top-1.5 -right-1.5 grid h-5 min-w-5 place-items-center rounded-full bg-suite-badge px-1 op-micro font-bold text-suite-badge-foreground tnum">{{ cartUnits }}</span>
        </span>
        <span class="min-w-0 flex-1">
          <span class="block truncate whitespace-nowrap op-title tnum">{{ cartUnits }} {{ cartUnits === 1 ? "item" : "itens" }} · {{ totalDisplay }}</span>
          <span v-if="fireBar.unfired && fireBar.visible" class="flex min-w-0 items-center gap-1 op-micro text-muted-foreground" data-pos-sheet-kitchen>
            <Icon name="lucide:chef-hat" class="size-3.5 shrink-0" /><span class="truncate">{{ fireBar.unfired }} ainda não {{ fireBar.unfired === 1 ? "foi" : "foram" }} à cozinha</span>
          </span>
          <span v-else-if="fireBar.fired" class="flex min-w-0 items-center gap-1 op-micro text-success" data-pos-sheet-kitchen>
            <Icon name="lucide:chef-hat" class="size-3.5 shrink-0" /><span class="truncate">{{ fireBar.fired }} na cozinha</span>
          </span>
        </span>
        <Icon name="lucide:chevron-up" class="size-5 shrink-0 text-muted-foreground" />
      </button>
      <!-- Com itens a enviar, "Enviar à cozinha" é a primária e o Pagamento fica ao
           lado, contornado (v4 `pos-tablet-fluxo` 1). Sem nada a enviar, o
           Pagamento volta a ser o sólido da zona do polegar (v4: 250 x 64). -->
      <div v-if="sheetFirePrimary" class="flex gap-2">
        <button
          type="button"
          class="flex h-14 min-w-0 flex-[1.6] items-center justify-center gap-2 rounded-lg bg-primary px-3 text-base font-semibold text-primary-foreground shadow-[0_2px_0_color-mix(in_oklab,var(--primary)_60%,black)] transition hover:bg-primary/90 disabled:opacity-50"
          :disabled="fireBar.disabled || firing"
          :aria-busy="firing || undefined"
          data-pos-sheet-fire
          @click="$emit('fire')"
        >
          <Icon :name="firing ? 'lucide:loader-circle' : 'lucide:chef-hat'" class="size-5 shrink-0" :class="firing ? 'animate-spin motion-reduce:animate-none' : ''" />
          <span class="truncate">{{ fireBar.label }}</span>
          <span class="grid h-6 min-w-6 shrink-0 place-items-center rounded-full bg-primary-foreground/20 px-1.5 op-label font-bold tnum">{{ fireBar.unfired }}</span>
        </button>
        <button
          type="button"
          class="flex h-14 min-w-0 flex-1 items-center justify-center gap-2 rounded-lg border border-border bg-card px-3 op-label font-semibold transition hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="!items.length || loading || saving"
          data-pos-sheet-primary
          @click="$emit('prepare')"
        >
          <Icon :name="primaryIconName" class="size-5 shrink-0" />
          <span class="truncate">{{ primaryText }}</span>
        </button>
      </div>
      <button
        v-else
        type="button"
        class="flex h-14 w-full shrink-0 items-center justify-center gap-2.5 rounded-lg bg-primary text-lg font-semibold text-primary-foreground shadow-[0_2px_0_color-mix(in_oklab,var(--primary)_60%,black)] transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none sm:h-16 sm:w-56"
        :disabled="!items.length || loading || saving"
        data-pos-sheet-primary
        @click="$emit('prepare')"
      >
        <Icon :name="primaryIconName" class="size-6 shrink-0" />
        {{ primaryText }}
      </button>
      </div>
    </template>
    <!-- Cabeçalho da comanda: contagem, Selecionar (Alt S) e Enviar à cozinha (F9). -->
    <header
      v-if="!batchMode && (!sheet || sheetOpen)"
      class="flex min-h-14 shrink-0 items-center gap-2 border-b border-border py-1.5 pr-2.5 pl-3.5"
    >
      <div class="min-w-0 leading-none">
        <h3 v-if="sheet" class="truncate op-title tnum whitespace-nowrap" data-pos-sheet-title>{{ tabTitle ? `${tabTitle} · ` : "" }}{{ cartUnits }} {{ cartUnits === 1 ? "item" : "itens" }}</h3>
        <template v-else>
          <h3 class="op-title tnum whitespace-nowrap">{{ cartUnits }} {{ cartUnits === 1 ? "item" : "itens" }}</h3>
          <p v-if="items.length" class="mt-1 whitespace-nowrap op-micro text-muted-foreground">em {{ items.length }} {{ items.length === 1 ? "linha" : "linhas" }}</p>
        </template>
      </div>
      <div class="flex-1" />
      <button
        ref="listEntry"
        type="button"
        aria-keyshortcuts="Alt+s"
        title="Selecionar linhas (Alt S): transferir, descontar e remover várias"
        class="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-md border border-border bg-card px-2 op-label transition hover:bg-accent"
        aria-label="Iniciar seleção"
        @click="toggleBatchMode"
      >
        <Icon name="lucide:list-checks" class="size-4" aria-hidden="true" />
        <span class="sr-only">Selecionar</span>
        <OperatorKbd v-if="!coarsePointer" aria-hidden="true">Alt S</OperatorKbd>
      </button>
      <!-- ENVIAR ganha calor quando HÁ o que enviar: item lançado e não enviado é
           trabalho parado. Borda e fundo primários, nunca o sólido: o sólido é do
           Pagamento. A contagem é badge (o número é o dado, o resto é rótulo). -->
      <div v-if="fireBar.visible" class="flex shrink-0 flex-col items-end gap-0.5">
      <button
        type="button"
        class="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-md border pr-1.5 pl-2.5 op-label font-semibold whitespace-nowrap transition disabled:cursor-not-allowed disabled:opacity-60"
        :class="fireBar.unfired && !fireBar.disabled
          ? 'border-primary bg-primary/10 hover:bg-primary/15'
          : 'border-border bg-card text-muted-foreground'"
        :disabled="fireBar.disabled || firing"
        :aria-busy="firing || undefined"
        title="Enviar à cozinha as linhas novas (F9)"
        data-pos-fire
        @click="$emit('fire')"
      >
        <Icon :name="firing ? 'lucide:loader-circle' : 'lucide:chef-hat'" class="size-4" :class="[fireBar.unfired && !fireBar.disabled ? 'text-primary' : '', firing ? 'animate-spin motion-reduce:animate-none' : '']" />
        {{ fireBar.label }}
        <span
          v-if="fireBar.unfired"
          class="grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-primary px-1 op-micro font-semibold tabular-nums text-primary-foreground"
          :aria-label="`${fireBar.unfired} item(ns) a enviar`"
          >{{ fireBar.unfired }}</span
        >
        <OperatorKbd v-if="!coarsePointer" aria-hidden="true">F9</OperatorKbd>
      </button>
      <!-- "envio automático: desligado" (v4 pino 1): o estado das estações desta
           comanda. O interruptor é por estação (decisão do dono), e mora em
           Ajustes › Envio à cozinha; o toque aqui leva até ele. -->
      <button
        v-if="!sheet"
        type="button"
        class="inline-flex items-center gap-1.5 op-micro text-muted-foreground hover:text-foreground"
        :title="autoFire ? 'Envio automático ligado na estação destes itens (Ajustes › Envio à cozinha)' : 'Envio automático desligado (Ajustes › Envio à cozinha)'"
        data-pos-auto-fire
        @click="$emit('autoFireSettings')"
      >
        <span class="relative inline-flex h-3.5 w-6 shrink-0 rounded-full transition" :class="autoFire ? 'bg-primary' : 'bg-muted-foreground/30'" aria-hidden="true">
          <span class="absolute top-0.5 size-2.5 rounded-full bg-card shadow transition-all" :class="autoFire ? 'left-3' : 'left-0.5'" />
        </span>
        envio automático: {{ autoFire ? "ligado" : "desligado" }}
      </button>
      </div>
      <button
        v-if="sheet"
        type="button"
        class="grid size-10 shrink-0 place-items-center rounded-md text-muted-foreground transition hover:bg-accent"
        aria-label="Recolher a comanda"
        @click="sheetOpen = false"
      >
        <Icon name="lucide:chevron-down" class="size-5" />
      </button>
    </header>

    <!-- Modo seleção (Alt S): o cabeçalho da comanda vira a barra do lote, numa faixa
         só (v4 `pos-sale4.html` pino 6): "× 2 selecionadas · Transferir F10 ·
         Desconto · Remover". Enviar só as marcadas e desfazer o envio continuam,
         como ícones na mesma faixa (o F9 envia todas as novas). -->
    <template v-else-if="!sheet || sheetOpen">
      <header class="flex min-h-14 shrink-0 items-center gap-1.5 border-b border-border bg-primary/10 px-2 py-1.5" data-pos-selection-bar>
        <button
          type="button"
          class="grid size-10 shrink-0 place-items-center rounded-md transition hover:bg-accent"
          aria-label="Concluir seleção"
          title="Sair da seleção (Esc)"
          @click="toggleBatchMode"
        >
          <Icon name="lucide:x" class="size-4" />
        </button>
        <p class="min-w-0 shrink truncate op-title tnum whitespace-nowrap">
          {{ selection.count ? `${selection.count} ${selection.count === 1 ? "selecionada" : "selecionadas"}` : "Toque nas linhas" }}
        </p>
        <div class="flex-1" />
        <button
          v-if="canMove && hasOpenTab"
          type="button"
          class="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-md border border-border bg-card px-2 op-label font-semibold transition hover:bg-accent disabled:opacity-50"
          :disabled="loading || !selection.count"
          title="Transferir as linhas marcadas para outra comanda (F10)"
          @click="$emit('move', selection.lineIds)"
        >
          <Icon name="lucide:split" class="size-4" />
          Transferir
          <OperatorKbd v-if="!coarsePointer" class="max-xl:hidden" aria-hidden="true">F10</OperatorKbd>
        </button>
        <button
          v-if="!lineAdjustmentsBlocked"
          type="button"
          class="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-md border px-2 op-label transition hover:bg-accent disabled:opacity-50"
          :class="discountOpen ? 'border-primary bg-primary/10 font-semibold' : 'border-border bg-card'"
          :aria-pressed="discountOpen"
          :disabled="!selection.count"
          @click="toggleDiscount"
        >
          <Icon name="lucide:percent" class="size-4" />
          Desconto
        </button>
        <button
          type="button"
          class="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-md border border-border bg-card px-2 op-label text-destructive transition hover:bg-destructive/10 disabled:opacity-50"
          :disabled="mutationBusy || !selection.count"
          @click="batchRemove"
        >
          <Icon name="lucide:trash-2" class="size-4" />Remover
        </button>
        <button
          v-if="fireAction.present && selection.canFire"
          type="button"
          class="grid size-10 shrink-0 place-items-center rounded-md border border-border bg-card text-primary transition hover:bg-accent disabled:opacity-50"
          :disabled="mutationBusy || firing || !fireAction.enabled"
          :aria-label="`Enviar à cozinha só as marcadas`"
          title="Enviar à cozinha só as marcadas"
          data-pos-batch-fire
          @click="batchFire"
        >
          <Icon name="lucide:chef-hat" class="size-4" />
        </button>
        <button
          v-if="selection.canUnfire && unfireAction.present"
          type="button"
          class="grid size-10 shrink-0 place-items-center rounded-md border border-border bg-card transition hover:bg-accent disabled:opacity-50"
          :disabled="mutationBusy || firing || !unfireAction.enabled"
          :aria-label="unfireAction.label || 'Cancelar envio à cozinha'"
          :title="unfireAction.label || 'Cancelar envio à cozinha'"
          @click="batchUnfire"
        >
          <Icon name="lucide:undo-2" class="size-4" />
        </button>
      </header>
    </template>

    <div
      v-show="!sheet || sheetOpen"
      ref="receiptList"
      class="min-h-0 flex-1 overflow-y-auto"
      data-receipt-list
      @keydown="navigateItems"
    >
      <p
        v-if="!items.length"
        class="p-6 text-center op-body text-muted-foreground"
      >
        Escolha um produto para começar.
      </p>
      <ul>
        <li
          v-for="item in items"
          :key="item.line_id"
          class="relative flex flex-wrap items-stretch border-b border-border"
          :aria-current="activeLineId === item.line_id ? 'true' : undefined"
          :class="
            isSelected(item.line_id)
              ? 'bg-primary/10'
              : activeLineId === item.line_id && editorVisible
                ? 'bg-primary/10 shadow-[inset_4px_0_0_var(--primary)]'
                : 'hover:bg-muted/50'
          "
          @click="batchMode && toggleSelect(item.line_id)"
        >
          <button
            v-if="batchMode"
            class="grid w-11 shrink-0 place-items-center"
            :aria-label="`Selecionar ${item.name}`"
            :aria-pressed="isSelected(item.line_id)"
            @click.stop="toggleSelect(item.line_id)"
          >
            <span
              class="grid size-5 place-items-center rounded border"
              :class="
                isSelected(item.line_id)
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-input bg-card'
              "
              ><Icon
                v-if="isSelected(item.line_id)"
                name="lucide:check"
                class="size-3.5"
            /></span>
          </button>
          <button
            class="grid min-h-12 min-w-0 flex-1 grid-cols-[2.25rem_minmax(0,1fr)_auto] items-center gap-x-2.5 py-1.5 pr-3.5 text-left focus-visible:outline-none"
            :class="batchMode ? 'pl-0' : 'pl-3.5'"
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
            <span v-if="isWeighedLine(item)" class="op-label font-semibold tnum"
              >{{ lineQtyLabel(item) }}</span
            >
            <span v-else class="op-title tnum"
              >{{ item.qty }}×</span
            >
            <span class="min-w-0">
              <span
                class="block truncate op-body leading-5"
                :class="activeLineId === item.line_id && editorVisible ? 'font-semibold' : 'font-medium'"
                :title="item.name"
                >{{ item.name }}</span
              >
              <!-- O fato da linha, numa linha só (v4): observação, desconto (preço
                   unitário só aqui ou no peso) e o estado na cozinha. -->
              <span
                v-if="item.notes || discountBadge(item) || isWeighedLine(item) || lineKitchenState(item) !== 'unfired' || goesToKitchen(item)"
                class="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-2 op-micro text-muted-foreground tnum"
              >
                <span v-if="item.notes" class="min-w-0 text-foreground/80 [overflow-wrap:anywhere]">Obs.: {{ item.notes }}</span>
                <span v-if="isWeighedLine(item)" class="shrink-0">{{ formatBRL(unitChargedQ(item)) }}/kg</span>
                <span
                  v-if="discountBadge(item)"
                  class="inline-flex shrink-0 items-center gap-1 font-semibold text-primary"
                  data-line-discount-fact
                  :title="discountBadge(item)"
                  ><Icon name="lucide:percent" class="size-3.5" aria-hidden="true" /><template v-if="!isWeighedLine(item)">{{ formatBRL(lineListUnitQ(item)) }} </template>{{ compactDiscount(item) }}</span
                >
                <!-- O fato da cozinha É a porta do card dela (estação, disparo, estado):
                     a linha não carrega enfeite à direita (v4). -->
                <span
                  v-if="lineKitchenState(item) !== 'unfired'"
                  role="button"
                  tabindex="-1"
                  class="inline-flex shrink-0 items-center gap-1 rounded-sm px-1"
                  :class="[badgeTone(kitchenBadge(item).tone), hasKitchenCard(item) ? 'cursor-pointer underline-offset-2 hover:underline' : '']"
                  :aria-label="hasKitchenCard(item) ? `Ver ${item.name} na cozinha` : undefined"
                  :data-testid="hasKitchenCard(item) ? 'kitchen-card-open' : undefined"
                  @click.stop="hasKitchenCard(item) && (kitchenLineId = item.line_id)"
                  ><Icon name="lucide:chef-hat" class="size-3.5" aria-hidden="true" />{{ kitchenFact(item) }}</span
                >
                <span
                  v-else-if="goesToKitchen(item)"
                  class="inline-flex shrink-0 items-center gap-1"
                  :title="`Vai para ${kitchenStations?.[item.sku]} quando for enviada`"
                  data-pos-line-goes-to-kitchen
                  ><Icon name="lucide:chef-hat" class="size-3.5" aria-hidden="true" />vai à cozinha</span
                >
              </span>
            </span>
            <strong class="op-title tnum">{{
              formatBRL(lineTotalQ(item))
            }}</strong>
          </button>
          <div
            v-if="expandedLineId === item.line_id"
            :id="detailsId(item.line_id)"
            role="region"
            :aria-label="`Detalhes de ${item.name}`"
            class="w-full px-3.5 pb-2 op-micro leading-relaxed"
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
            <div v-if="!batchMode && !lineAdjustmentsBlocked" class="mt-1 flex justify-between">
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

    <!-- EDITOR DA LINHA, sob demanda (v4): colado no pé da lista, borda primária em
         cima. Clicar (ou ↑↓) numa linha abre o editor DELA; Fechar (Esc) devolve a
         lista inteira. Com a seleção ligada, o mesmo lugar recebe o desconto do lote. -->
    <section
      v-if="(editorVisible || (batchMode && discountOpen)) && (!sheet || sheetOpen)"
      class="shrink-0 border-t-2 border-primary bg-card px-3 pt-2 pb-2.5 shadow-[0_-10px_24px_rgb(0_0_0/.10)]"
      aria-label="Console do item"
      data-pos-line-editor
    >
      <!-- TOQUE (v4 tablet b): um instrumento só. A caixa grande mostra o número; o
           numérico 3×4 escreve nele; a coluna à direita tem Desconto, Observação,
           Remover e Pronto. -->
      <template v-if="touchEditor && activeItem">
        <div class="flex items-center gap-3" data-pos-touch-editor>
          <p class="min-w-0 flex-1 truncate op-label text-muted-foreground">
            <template v-if="inDiscountMode">Desconto em <b class="font-semibold text-foreground">{{ activeItem.name }}</b></template>
            <template v-else-if="isWeighedLine(activeItem)">Peça pesada: para trocar, remova e lance a outra etiqueta.</template>
            <template v-else>Quantidade de <b class="font-semibold text-foreground">{{ activeItem.name }}</b> <span class="tnum">(era {{ qtyWas }})</span></template>
          </p>
          <output
            class="grid h-12 min-w-20 shrink-0 place-items-center rounded-md border-2 border-foreground/80 bg-card px-3 text-2xl font-semibold tnum"
            :aria-label="inDiscountMode ? 'Desconto' : `Quantidade de ${activeItem.name}`"
            data-pos-touch-editor-value
          >{{ touchEditorValue }}</output>
        </div>
        <p v-if="activeAuthorship || lineKitchenState(activeItem) === 'fired_cancellable'" class="mt-1 flex items-center gap-2 op-micro text-muted-foreground">
          <span class="min-w-0 flex-1 truncate">{{ activeAuthorship }}</span>
          <button
            v-if="lineKitchenState(activeItem) === 'fired_cancellable'"
            type="button"
            class="shrink-0 font-medium text-primary disabled:opacity-50"
            :disabled="mutationBusy || firing || !unfireAction.enabled"
            @click="$emit('unfire', activeItem.line_id)"
          >{{ unfireAction.label }}</button>
        </p>
      </template>
      <template v-else-if="!batchMode && activeItem">
        <p class="flex h-6 items-center gap-1.5 truncate op-micro text-muted-foreground">
          <Icon name="lucide:corner-left-up" class="size-3.5 shrink-0 text-primary" aria-hidden="true" />
          Editando <b class="truncate font-semibold text-foreground">{{ activeItem.name }}</b>
          <span class="shrink-0 tnum">· {{ formatBRL(unitChargedQ(activeItem)) }}{{ isWeighedLine(activeItem) ? "/kg" : " cada" }}</span>
        </p>
        <div class="mt-1.5 flex items-center gap-2" aria-label="Ajustes do item">
          <span
            v-if="isWeighedLine(activeItem)"
            class="min-w-0 flex-1 op-micro text-muted-foreground"
          >Peça pesada: para trocar, remova e lance a outra etiqueta.</span>
          <div
            v-else
            class="inline-flex h-11 shrink-0 items-center overflow-hidden rounded-md border border-input bg-card"
            role="group"
            :aria-label="`Quantidade de ${activeItem.name}`"
            title="Quantidade: −/+ ou digite"
          >
            <button
              type="button"
              class="grid size-11 place-items-center border-r border-border hover:bg-accent disabled:opacity-50"
              aria-label="Diminuir"
              :disabled="mutationBusy"
              @click="bump(activeItem.line_id, 'decrement')"
            >
              <Icon name="lucide:minus" class="size-4" />
            </button>
            <button
              type="button"
              class="h-11 w-11 text-center op-title tnum disabled:opacity-50"
              :class="numpadMode === 'qty' && !numpadFresh ? 'bg-primary/10' : ''"
              :aria-label="`Editar quantidade de ${activeItem.name}`"
              :disabled="mutationBusy"
              @click="
                selectLine(activeItem.line_id);
                setMode('qty');
              "
            >
              {{ activeItem.qty }}
            </button>
            <button
              type="button"
              class="grid size-11 place-items-center border-l border-border hover:bg-accent disabled:opacity-50"
              aria-label="Aumentar"
              :disabled="mutationBusy"
              @click="bump(activeItem.line_id, 'increment')"
            >
              <Icon name="lucide:plus" class="size-4" />
            </button>
          </div>
          <button
            type="button"
            class="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-md px-2.5 op-label font-semibold whitespace-nowrap text-destructive transition hover:bg-destructive/10 disabled:opacity-50"
            aria-label="Remover"
            title="Remover, com confirmação e desfazer"
            :disabled="mutationBusy"
            @click="askRemove(activeItem.line_id)"
          >
            <Icon name="lucide:trash-2" class="size-4" />Remover
            <OperatorKbd v-if="!coarsePointer" class="max-xl:hidden" aria-hidden="true">Del</OperatorKbd>
          </button>
          <div class="flex-1" />
          <button
            type="button"
            class="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-md px-2 op-label whitespace-nowrap text-muted-foreground transition hover:bg-accent"
            title="Fechar o editor"
            data-pos-line-editor-close
            @click="closeEditor"
          >
            Fechar
            <OperatorKbd v-if="!coarsePointer" class="max-xl:hidden" aria-hidden="true">Esc</OperatorKbd>
          </button>
        </div>
        <div v-if="!lineAdjustmentsBlocked" class="mt-2 grid grid-cols-2 gap-2">
          <button
            type="button"
            class="inline-flex h-10 items-center justify-center gap-1.5 rounded-md border px-2.5 op-label whitespace-nowrap transition hover:bg-accent disabled:opacity-50"
            :class="discountOpen || activeItem.discount?.value ? 'border-primary bg-primary/10 font-semibold' : 'border-border bg-card'"
            :aria-pressed="discountOpen"
            :disabled="mutationBusy"
            data-pos-line-discount
            @click="toggleDiscount"
          >
            <Icon name="lucide:percent" class="size-4 text-primary" />
            {{ discountButtonLabel }}
          </button>
          <button
            type="button"
            class="inline-flex h-10 items-center justify-center gap-1.5 rounded-md border border-border bg-card px-2.5 op-label whitespace-nowrap transition hover:bg-accent disabled:opacity-50"
            :disabled="mutationBusy"
            @click="chooseMode('note')"
          >
            <Icon name="lucide:message-square-text" class="size-4" />
            Observação
          </button>
        </div>
        <p v-if="activeAuthorship || lineKitchenState(activeItem) === 'fired_cancellable'" class="mt-1.5 flex items-center gap-2 op-micro text-muted-foreground" data-pos-line-authorship>
          <span class="min-w-0 flex-1 truncate">{{ activeAuthorship }}</span>
          <button
            v-if="lineKitchenState(activeItem) === 'fired_cancellable'"
            type="button"
            class="shrink-0 font-medium text-primary disabled:opacity-50"
            :disabled="mutationBusy || firing || !unfireAction.enabled"
            @click="$emit('unfire', activeItem.line_id)"
          >{{ unfireAction.label }}</button>
        </p>
      </template>

      <!-- Desconto (da linha ou do lote): formato, valor e motivo. O numérico da tela
           aparece aqui e, nos dispositivos de toque, também para a quantidade. -->
      <div v-if="discountOpen && !lineAdjustmentsBlocked" class="mt-2 grid gap-2" data-pos-discount-panel>
        <div class="flex items-center gap-2">
          <div class="inline-flex h-10 shrink-0 items-center gap-1 rounded-md bg-secondary p-1" role="group" aria-label="Formato do desconto">
            <button
              v-for="mode in discountModes"
              :key="mode.ref"
              type="button"
              class="inline-flex h-full items-center rounded px-2.5 op-label transition disabled:opacity-50"
              :class="numpadMode === mode.ref ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground'"
              :aria-pressed="numpadMode === mode.ref"
              :disabled="mutationBusy"
              @click="chooseMode(mode.ref)"
            >
              {{ mode.label }}
            </button>
          </div>
          <p class="min-w-0 flex-1 truncate text-right op-micro text-muted-foreground">
            {{
              selectMode
                ? `Desconto em ${selection.units} itens`
                : numpadMode === "disc_brl"
                  ? "Desconto por unidade"
                  : "Desconto percentual"
            }}:
            <strong class="op-title text-foreground tnum">{{
              numpadMode === "disc_brl"
                ? `R$ ${numpadBuffer || "0"}`
                : `${numpadBuffer || "0"}%`
            }}</strong>
          </p>
        </div>
        <UiNativeSelect
          v-model="discountReason"
          aria-label="Motivo do desconto"
          :disabled="mutationBusy"
          class="w-full text-sm"
          @change="commitDiscount"
        >
          <option
            v-for="reason in reasonOptions"
            :key="reason.ref"
            :value="reason.ref"
          >
            {{ reason.label }}
          </option>
        </UiNativeSelect>
      </div>

      <div v-if="touchEditor && activeItem" class="mt-2 grid grid-cols-[repeat(3,minmax(0,1fr))_minmax(0,1.6fr)] gap-2" data-pos-line-numpad>
        <template v-for="(row, rowIndex) in [[1, 2, 3], [4, 5, 6], [7, 8, 9], ['decimal', 0, 'back']]" :key="rowIndex">
          <button
            v-for="key in row"
            :key="String(key)"
            type="button"
            class="h-14 rounded-md border border-border bg-card text-2xl font-medium tnum transition hover:bg-muted active:bg-muted disabled:opacity-40 sm:h-16"
            :aria-label="typeof key === 'number' ? 'Dígito ' + key : key === 'back' ? 'Apagar último dígito' : 'Vírgula'"
            :disabled="mutationBusy || !numpadCanType || (key === 'decimal' && numpadMode !== 'disc_brl')"
            @click="typeof key === 'number' ? onDigit(String(key)) : key === 'back' ? onBackspace() : onComma()"
          >
            <Icon v-if="key === 'back'" name="lucide:delete" class="mx-auto size-6" />
            <template v-else>{{ key === "decimal" ? "," : key }}</template>
          </button>
          <button
            v-if="rowIndex === 0"
            type="button"
            class="inline-flex h-14 items-center justify-center gap-1.5 rounded-md border px-2 op-label font-semibold transition disabled:opacity-40 sm:h-16"
            :class="discountOpen || activeItem.discount?.value ? 'border-primary bg-primary/15' : 'border-transparent bg-secondary'"
            :aria-pressed="discountOpen"
            :disabled="mutationBusy || lineAdjustmentsBlocked"
            data-pos-line-discount
            @click="toggleDiscount"
          ><Icon name="lucide:percent" class="size-4 shrink-0" /><span class="truncate">{{ discountOpen ? "Quantidade" : "Desconto" }}</span></button>
          <button
            v-else-if="rowIndex === 1"
            type="button"
            class="inline-flex h-14 items-center justify-center gap-1.5 rounded-md border border-transparent bg-secondary px-2 op-label font-semibold transition disabled:opacity-40 sm:h-16"
            :disabled="mutationBusy || lineAdjustmentsBlocked"
            @click="chooseMode('note')"
          ><Icon name="lucide:message-square-text" class="size-4 shrink-0" /><span class="truncate">Observação</span></button>
          <button
            v-else-if="rowIndex === 2"
            type="button"
            class="inline-flex h-14 items-center justify-center gap-1.5 rounded-md border border-destructive/30 bg-card px-2 op-label font-semibold text-destructive transition hover:bg-destructive/10 disabled:opacity-40 sm:h-16"
            :disabled="mutationBusy"
            @click="askRemove(activeItem.line_id)"
          ><Icon name="lucide:trash-2" class="size-4 shrink-0" /><span class="truncate">Remover</span></button>
          <button
            v-else
            type="button"
            class="inline-flex h-14 items-center justify-center gap-1.5 rounded-md bg-foreground px-2 op-label font-semibold text-background transition hover:bg-foreground/90 sm:h-16"
            data-pos-line-editor-close
            @click="closeEditor"
          ><Icon name="lucide:check" class="size-4 shrink-0" />Pronto</button>
        </template>
      </div>
      <div v-if="numpadVisible" class="mt-2 grid grid-cols-3 gap-1.5" data-pos-line-numpad>
        <button
          v-for="key in [1, 2, 3, 4, 5, 6, 7, 8, 9, 'decimal', 0, 'back']"
          :key="key"
          type="button"
          class="h-11 rounded-md border bg-card op-title transition hover:bg-muted disabled:opacity-40"
          :class="
            key === 'back' ? 'border-destructive/30 text-destructive' : 'border-border'
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

      <p
        v-if="lineAdjustmentsBlockedReason"
        class="mt-2 flex items-start gap-1.5 op-micro text-muted-foreground"
        data-line-adjustments-blocked
      >
        <Icon name="lucide:info" class="mt-0.5 size-3.5 shrink-0" />
        <span>{{ lineAdjustmentsBlockedReason }}</span>
      </p>
    </section>

    <!-- O teclado físico edita a linha ativa: a dica mora aqui, no balcão (v4). -->
    <p
      v-if="items.length && !batchMode && !coarsePointer && !sheet"
      class="hidden h-7 shrink-0 items-center gap-2 overflow-hidden border-t border-border bg-muted/50 px-3.5 op-micro whitespace-nowrap text-muted-foreground md:flex"
      data-pos-keyboard-hint
    >
      Digite para mudar a quantidade <span class="text-border" aria-hidden="true">·</span> Del remove <span class="text-border" aria-hidden="true">·</span> ↑↓ troca a linha
    </p>

    <!-- Pé: UMA faixa, o maior alvo da tela (Pagamento F4 com o total dentro). Na
         seleção, o pé encolhe para o total: o gesto geral espera o Concluir. -->
    <div v-if="batchMode" class="flex shrink-0 items-baseline justify-between border-t border-border px-3.5 py-3">
      <span class="op-label text-muted-foreground">Total parcial</span>
      <strong class="text-xl font-semibold tnum">{{ totalDisplay }}</strong>
    </div>
    <!-- FOLHA ABERTA (v4 tablet b): pagar direto daqui, pelos meios eletrônicos que
         o dispositivo leva à mesa. "Outras formas" abre o Pagamento de sempre. -->
    <div v-else-if="sheet && sheetOpen && quickPayments?.length && !primaryLabel" class="shrink-0 border-t border-border p-3" data-pos-sheet-pay>
      <div class="mb-2 flex items-baseline gap-2">
        <span class="op-label text-muted-foreground">Pagar</span>
        <strong class="text-2xl font-semibold tnum">{{ totalDisplay }}</strong>
        <span class="flex-1" />
        <button
          type="button"
          class="min-h-10 rounded-md px-2 op-label font-medium text-primary hover:bg-accent disabled:opacity-50"
          :disabled="!items.length || loading || saving"
          data-pos-sheet-other-payment
          @click="$emit('prepare')"
        >Outras formas</button>
      </div>
      <div class="grid gap-2" :class="quickPayments.length > 1 ? 'grid-cols-2' : 'grid-cols-1'">
        <button
          v-for="method in quickPayments"
          :key="method.ref"
          type="button"
          class="flex h-14 items-center justify-center gap-2.5 rounded-lg bg-primary text-lg font-semibold text-primary-foreground shadow-[0_2px_0_color-mix(in_oklab,var(--primary)_60%,black)] transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none"
          :disabled="!items.length || loading || saving"
          :data-pos-sheet-pay-method="method.ref"
          @click="$emit('pay', method.ref)"
        >
          <Icon :name="method.icon" class="size-6 shrink-0" />
          {{ method.label }}
        </button>
      </div>
    </div>
    <div v-else-if="!sheet || sheetOpen" class="shrink-0 border-t border-border p-3">
      <button
        type="button"
        class="flex h-16 w-full items-center gap-3 rounded-lg bg-primary pr-3.5 pl-4 text-primary-foreground shadow-[0_2px_0_color-mix(in_oklab,var(--primary)_60%,black)] transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none"
        :disabled="!items.length || loading || saving"
        :aria-busy="loading || undefined"
        :title="`${primaryText} (F4)`"
        data-pos-primary
        @click="$emit('prepare')"
      >
        <Icon :name="loading ? 'lucide:loader-circle' : primaryIconName" class="size-6 shrink-0" :class="loading ? 'animate-spin motion-reduce:animate-none' : ''" />
        <span class="text-lg font-semibold whitespace-nowrap">{{ primaryText }}</span>
        <OperatorKbd v-if="!coarsePointer" variant="inverse" class="max-lg:hidden" aria-hidden="true">F4</OperatorKbd>
        <span class="flex-1" />
        <span class="flex flex-col items-end leading-none">
          <span class="op-micro opacity-80">total</span>
          <span class="text-xl leading-8 font-semibold tnum xl:text-3xl">{{ totalDisplay }}</span>
        </span>
      </button>
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

  <PosKitchenTicketDialog
    :open="kitchenLine != null"
    :line-name="kitchenLine?.name ?? ''"
    :tickets="kitchenLine?.kitchen_tickets ?? []"
    @update:open="(value) => { if (!value) kitchenLineId = ''; }"
  />
</template>
