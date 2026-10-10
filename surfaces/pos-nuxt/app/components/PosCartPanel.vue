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
import { saleTotalText, type SaleTotalView } from "~/presentation/saleTotal";
import { isWeighedLine, lineQtyLabel } from "~/presentation/weighed";
import { toast } from "vue-sonner";
import { createReusableTemplate } from "@vueuse/core";

import type { OperatorActionBarAction } from "../../../operator-kit/app/presentation/actionBar";

const props = defineProps<{
  items: POSCartItem[];
  /** O total da revisão do servidor, ou o estado sem número (`saleTotalView`). */
  total: SaleTotalView;
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
  quickPayments?: Array<{ ref: string; label: string; icon: string; hint?: string; secondary?: boolean }>;
}>();
// Folha aberta: PIX e Maquininha são o gesto principal; o dinheiro (V6-CAIXA)
// vem embaixo, secundário.
const primaryQuickPayments = computed(() => (props.quickPayments || []).filter((m) => !m.secondary));
const secondaryQuickPayments = computed(() => (props.quickPayments || []).filter((m) => m.secondary));
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
  /** Dividir a conta: o modal do Pagamento, aberto a partir da comanda. */
  split: [];
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

// O total da comanda é o do SERVIDOR (a revisão), nunca a soma local: regra do
// dono (09/10), total que ainda pode mudar não aparece como definitivo. Sem a
// revisão, o lugar do número diz "Calculando…" (ou "Não calculado", quando ela
// falhou; o Pagamento diz o motivo e oferece "Tentar de novo").
const totalText = computed(() => saleTotalText(props.total));
// Sem conexão o número aparece (a venda de balcão segue), com o rótulo dizendo de
// onde ele veio: é a soma da tela pela última leitura de preços.
const totalConfirmed = computed(() => props.total.status === "confirmed" || props.total.status === "offline");
const totalShown = computed(() => props.total.status !== "hidden");

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

// O corpo da comanda é um só: a coluna da mesa e a gaveta do celular reusam o mesmo
// molde (`DefineTicketBody` / `ReuseTicketBody`).
const [DefineTicketBody, ReuseTicketBody] = createReusableTemplate();
const [DefineFireButton, ReuseFireButton] = createReusableTemplate();
const [DefineControlGrid, ReuseControlGrid] = createReusableTemplate<{ rows: ControlCell[][]; block: "line" | "tab" }>();
// O estado da cozinha em palavra (o que falta e o que já foi), no lugar do botão
// apagado de quando não há nada a enviar.
// A GRADE DE CONTROLES DA COMANDA (dono, 10/10): duas colunas de mesma largura,
// tudo alinhado, em dois blocos com um separador discreto entre eles.
// · O bloco da LINHA, só com uma linha aberta no editor (mouse e teclado):
//   quantidade | Remover; Desconto | Observação.
// · O bloco da COMANDA, sempre, numa posição fixa logo acima do Pagamento (não pula
//   quando o editor abre ou fecha): Enviar à cozinha | Dividir. As duas na mesma
//   linha porque são da comanda e às vezes são as únicas.
// Célula sem par ocupa as duas colunas: sem buraco.
type ControlCell = "qty" | "remove" | "fire" | "discount" | "split" | "note";
const lineControlsInGrid = computed(() => Boolean(activeItem.value) && editorVisible.value && !touchEditor.value && !batchMode.value);
const canSplit = computed(() => !props.primaryLabel && props.items.length > 0);
const lineRows = computed<ControlCell[][]>(() => {
  if (!lineControlsInGrid.value) return [];
  return lineAdjustmentsBlocked.value ? [["qty", "remove"]] : [["qty", "remove"], ["discount", "note"]];
});
// A edição em curso da linha (o desconto ou a observação) toma o lugar da grade.
const lineEditing = computed<"discount" | "note" | "">(() => {
  if (noteDraft.value) return "note";
  if (discountOpen.value && !lineAdjustmentsBlocked.value) return "discount";
  return "";
});
// A dica do teclado diz o que as teclas fazem AGORA.
const keyboardHint = computed<string[]>(() => {
  if (lineEditing.value === "discount") return ["Digite o desconto", "Enter aplica", "Esc cancela"];
  if (lineEditing.value === "note") return ["Enter aplica", "Shift Enter quebra a linha", "Esc cancela"];
  return ["Digite a quantidade", "Del remove", "↑↓ troca a linha"];
});
// A SELEÇÃO age no mesmo bloco do editor: as ações nas linhas marcadas, em grade.
const batchRows = computed<BatchCell[][]>(() => {
  const cells: BatchCell[] = [];
  if (canMove.value && props.hasOpenTab) cells.push("move");
  if (!lineAdjustmentsBlocked.value) cells.push("discount");
  cells.push("remove");
  if (props.fireAction.present && selection.value.canFire) cells.push("fire");
  if (selection.value.canUnfire && props.unfireAction.present) cells.push("unfire");
  const rows: BatchCell[][] = [];
  for (let i = 0; i < cells.length; i += 2) rows.push(cells.slice(i, i + 2));
  return rows;
});
type BatchCell = "move" | "discount" | "remove" | "fire" | "unfire";
const tabRows = computed<ControlCell[][]>(() => {
  if (batchMode.value) return [];
  const row: ControlCell[] = [];
  if (fireBar.value.visible) row.push("fire");
  if (canSplit.value) row.push("split");
  return row.length ? [row] : [];
});
// O rótulo que cabe (`OperatorButton`/`OperatorFitGroup` do kit): as ações da grade
// com o curto escrito à mão; o que vai ao lado do rótulo (contagem, tecla) entra na
// conta pelo `reserve` do grupo, em rem.
const COUNT_RESERVE_REM = 2;
const REMOVE_FIT = { label: "Remover", icon: "i-lucide-trash-2" } as const;
const fireFit = computed(() => ({
  label: fireBar.value.label,
  shortLabel: fireBar.value.unfired ? "Enviar" : undefined,
  icon: props.firing ? undefined : "i-lucide-chef-hat",
}));
const fireReserve = computed(() => (fireBar.value.unfired ? COUNT_RESERVE_REM : 0));
const kitchenStateText = computed(() => {
  const { unfired, fired } = fireBar.value;
  const parts: string[] = [];
  if (unfired) parts.push(`${unfired} a enviar`);
  if (fired) parts.push(`${fired} na cozinha`);
  return parts.join(" · ");
});

// A folha fechada é a barra da ação do momento (`OperatorActionBar`): a linha de
// contexto diz a comanda, os itens e a cozinha; o número é o total da revisão do
// servidor, e só quando confirmado. Enquanto a revisão corre, "Calculando…" fica na
// linha de contexto, em texto comum: nunca no lugar do número, como se fosse final.
const sheetTitle = computed(() => `${props.tabTitle ? `${props.tabTitle} · ` : ""}${cartUnits.value} ${cartUnits.value === 1 ? "item" : "itens"}`);
const sheetContextLabel = computed(() => {
  const bar = fireBar.value;
  const kitchen = bar.visible && bar.unfired
    ? `${bar.unfired} ainda não ${bar.unfired === 1 ? "foi" : "foram"} à cozinha`
    : bar.fired
      ? `${bar.fired} na cozinha`
      : "";
  const pendingTotal = totalShown.value && !totalConfirmed.value ? totalText.value : "";
  return [sheetTitle.value, kitchen, pendingTotal].filter(Boolean).join(" · ");
});
const sheetAction = computed<OperatorActionBarAction>(() => {
  if (sheetFirePrimary.value) {
    return {
      label: fireBar.value.label,
      icon: "i-lucide-chef-hat",
      loading: props.firing,
      disabled: fireBar.value.disabled || props.firing,
      onSelect: () => emit("fire"),
    };
  }
  return {
    label: primaryText.value,
    icon: primaryIconName.value,
    loading: props.loading,
    disabled: !props.items.length || props.loading || props.saving,
    reason: props.items.length ? undefined : "Escolha um produto para começar.",
    onSelect: () => emit("prepare"),
  };
});
const sheetSecondary: OperatorActionBarAction = {
  label: "Ver a comanda",
  icon: "i-lucide-receipt-text",
  onSelect: () => {
    sheetOpen.value = true;
  },
};

// ── Editor da linha, sob demanda (v4) ─────────────────────────────────────────
// Aberto para a linha ativa (a tocada, ou a última lançada); "Fechar" (Esc) devolve
// a lista inteira até a próxima linha tocada, o próximo produto lançado ou o próximo
// dígito do teclado físico (o teclado continua editando a linha ativa, como sempre).
// No toque (tablet, prévia `pos-tablet.jpg`) o editor e o numérico só aparecem ao
// tocar a linha: a lista fica inteira enquanto se lança.
const coarsePointer = useMediaQuery("(pointer: coarse)");
// O tamanho dos controles da comanda no conjunto mínimo: `md` no mouse, `xl` no toque.
const controlSize = computed(() => (coarsePointer.value ? "xl" : "md"));
// A coluna de ações do numérico do toque: rótulo de ação não se corta ("Obser…" não
// diz nada); na coluna estreita do celular ele quebra a linha em vez de truncar.
const SIDE_KEY_UI = { label: "whitespace-normal text-clip text-center leading-tight", leadingIcon: "size-4" };
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
// EDITAR UMA LINHA É SEMPRE NO MESMO LUGAR (dono, 10/10): o desconto e a observação
// abrem no bloco do editor, no lugar da grade, e terminam em Cancelar ou Aplicar. Na
// mesa (mouse e teclado) o desconto é um RASCUNHO: o número e o motivo só valem no
// Aplicar (Enter); Cancelar (Esc) devolve a linha como estava. No toque, o numérico
// do editor de toque segue gravando a cada tecla (um instrumento só, "Pronto" fecha).
const discountDraft = computed(() => !touchEditor.value);
function applyDiscount() {
  commitDiscount();
  discountOpen.value = false;
  if (!selectMode.value) setMode("qty");
}
function cancelDiscount() {
  discountOpen.value = false;
  if (!selectMode.value) setMode("qty");
  else syncBufferToMode();
}
// Na célula estreita o desconto vigente diz só o valor ("10%"), com o ícone.
const discountShortLabel = computed(() => {
  const discount = activeItem.value?.discount;
  if (!discount?.value) return "";
  return discount.type === "fixed"
    ? formatBRL(Math.round(discount.value * 100))
    : `${String(discount.value).replace(".", ",")}%`;
});
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

// Observação da linha (Odoo Note): o texto da linha ativa, escrito NO EDITOR (o mesmo
// lugar do desconto), com Cancelar ou Aplicar. Enter aplica; Shift Enter quebra a linha.
// O dado já existia (POSCartItem.notes, intent, KDS).
const noteDraft = ref<{ lineId: string; name: string; text: string } | null>(null);
const noteField = ref<{ textareaRef?: HTMLTextAreaElement; $el?: HTMLElement } | null>(null);
function openNoteDialog() {
  if (lineAdjustmentsBlocked.value) return;
  const item = activeItem.value;
  if (!item) return;
  discountOpen.value = false;
  if (inDiscountMode.value && !selectMode.value) setMode("qty");
  editorClosed.value = false;
  noteDraft.value = { lineId: item.line_id, name: item.name, text: item.notes || "" };
  void nextTick(() => {
    const field = noteField.value?.textareaRef || noteField.value?.$el?.querySelector?.("textarea");
    field?.focus();
  });
}
function saveNote() {
  const draft = noteDraft.value;
  noteDraft.value = null;
  if (!draft) return;
  emit("setNotes", draft.lineId, draft.text.trim());
}
function cancelNote() {
  noteDraft.value = null;
}
function onNoteKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    saveNote();
  } else if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    cancelNote();
  }
}
// Trocar de linha fecha a edição que estava aberta (nada fica pendurado em outra linha).
watch(activeLineId, () => {
  if (noteDraft.value && noteDraft.value.lineId !== activeLineId.value) noteDraft.value = null;
});

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
    if (!discountDraft.value) commitDiscount();
    return;
  }
  numpadBuffer.value = pushDigit(numpadBuffer.value, digit, {
    fresh: numpadFresh.value,
    maxLength: 3,
  });
  numpadFresh.value = false;
  if (numpadMode.value === "qty") commitQty();
  else if (!discountDraft.value) commitDiscount();
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
  if (!discountDraft.value) commitDiscount();
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
    if (!discountDraft.value) commitDiscount();
    return;
  }
  numpadBuffer.value = popDigit(numpadBuffer.value);
  numpadFresh.value = false;
  if (numpadMode.value === "qty") commitQty();
  else if (!discountDraft.value) commitDiscount();
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
  if (discountOpen.value && discountDraft.value && (event.key === "Enter" || event.key === "Escape")) {
    // O desconto em rascunho: Enter aplica, Esc cancela (a dica do editor diz isso).
    event.preventDefault();
    if (event.key === "Enter") applyDiscount();
    else cancelDiscount();
    return;
  }
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
  listEntry.value?.$el?.focus();
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
// O `NuxtButton` do "Selecionar": o foco volta ao elemento dele (`$el`).
const listEntry = ref<{ $el?: HTMLElement } | null>(null);
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
  <!-- O CORPO da comanda, escrito uma vez: na mesa é a coluna; abaixo do desktop é o
       que a gaveta de baixo (`NuxtDrawer`) mostra quando a comanda é puxada. -->
  <!-- ENVIAR À COZINHA: só aparece quando HÁ o que enviar (a contagem no chip), em
       contorno primário; o sólido é do Pagamento. Com tudo enviado, quem diz é o
       estado em palavra ("11 na cozinha"), não um botão apagado. -->
  <DefineFireButton>
    <!-- O grupo do kit é o contêiner: o rótulo conta com a contagem ao lado
         (`reserve`). Quando aperta, o F9 cai primeiro; o verbo fica ("Enviar 5"). -->
    <OperatorFitGroup :actions="[fireFit]" :size="controlSize" :reserve="fireReserve" class="h-full w-full">
      <OperatorButton
        v-bind="fireFit"
        :size="controlSize"
        :color="fireBar.unfired && !fireBar.disabled ? 'primary' : 'neutral'"
        variant="outline"
        :loading="firing"
        block
        class="h-full justify-center bg-default font-semibold"
        :disabled="fireBar.disabled || firing"
        :aria-busy="firing || undefined"
        :shortcut="coarsePointer || !fireBar.unfired ? undefined : 'F9'"
        aria-keyshortcuts="F9"
        :title="`${fireBar.label} as linhas novas (F9)`"
        data-pos-fire
        @click="$emit('fire')"
      >
        <template v-if="fireBar.unfired" #trailing>
          <OperatorCountChip
            :count="fireBar.unfired"
            :aria-label="`${fireBar.unfired} ${fireBar.unfired === 1 ? 'item' : 'itens'} a enviar`"
          />
        </template>
      </OperatorButton>
    </OperatorFitGroup>
  </DefineFireButton>
  <!-- A GRADE DE CONTROLES (dono, 10/10): duas colunas de mesma largura, bordas e
       alturas batendo. Cada célula é um `@container`: o rótulo cabe na largura DELA
       (completo, curto escrito à mão ou só o ícone), nunca corta. -->
  <DefineControlGrid v-slot="{ rows, block }">
    <div class="grid grid-cols-2 gap-2" data-pos-ticket-controls :data-pos-controls-block="block">
      <template v-for="(row, rowIndex) in rows" :key="rowIndex">
        <div
          v-for="cell in row"
          :key="cell"
          class="@container min-w-0"
          :class="row.length === 1 ? 'col-span-2' : ''"
          :data-pos-control-cell="cell"
        >
          <template v-if="cell === 'qty' && activeItem">
            <p
              v-if="isWeighedLine(activeItem)"
              class="flex h-full items-center op-micro text-muted-foreground"
            >Peça pesada: para trocar, remova e lance a outra etiqueta.</p>
            <NuxtFieldGroup
              v-else
              class="flex h-full w-full"
              :aria-label="`Quantidade de ${activeItem.name}`"
              title="Quantidade: −/+ ou digite"
              data-pos-line-qty
            >
              <NuxtButton
                :size="controlSize"
                color="neutral"
                variant="outline"
                icon="i-lucide-minus"
                square
                aria-label="Diminuir"
                :disabled="mutationBusy"
                @click="bump(activeItem.line_id, 'decrement')"
              />
              <NuxtButton
                :size="controlSize"
                color="neutral"
                variant="outline"
                class="min-w-0 flex-1 justify-center op-title tnum"
                active-color="primary"
                active-variant="solid"
                :active="numpadMode === 'qty' && !numpadFresh"
                :aria-label="`Editar quantidade de ${activeItem.name}`"
                :disabled="mutationBusy"
                :label="String(activeItem.qty)"
                @click="
                  selectLine(activeItem.line_id);
                  setMode('qty');
                "
              />
              <NuxtButton
                :size="controlSize"
                color="neutral"
                variant="outline"
                icon="i-lucide-plus"
                square
                aria-label="Aumentar"
                :disabled="mutationBusy"
                @click="bump(activeItem.line_id, 'increment')"
              />
            </NuxtFieldGroup>
          </template>
          <div v-else-if="cell === 'remove' && activeItem" class="op-fit-scope h-full w-full">
            <OperatorButton
              v-bind="REMOVE_FIT"
              :size="controlSize"
              color="error"
              variant="outline"
              block
              class="h-full justify-center bg-default font-semibold"
              :shortcut="coarsePointer ? undefined : 'Del'"
              aria-keyshortcuts="Delete"
              title="Remover (Del), com confirmação e desfazer"
              :disabled="mutationBusy"
              data-pos-line-remove
              @click="askRemove(activeItem.line_id)"
            />
          </div>
          <ReuseFireButton v-else-if="cell === 'fire'" />
          <OperatorButton
            v-else-if="cell === 'discount' && activeItem"
            :label="discountButtonLabel"
            :short-label="discountShortLabel || undefined"
            icon="i-lucide-percent"
            :size="controlSize"
            color="neutral"
            variant="outline"
            active-color="primary"
            active-variant="solid"
            :active="discountOpen"
            block
            class="h-full justify-center"
            :class="!discountOpen && activeItem.discount?.value ? 'font-semibold' : ''"
            :aria-pressed="discountOpen"
            :disabled="mutationBusy"
            data-pos-line-discount
            @click="toggleDiscount"
          />
          <OperatorButton
            v-else-if="cell === 'split'"
            label="Dividir conta"
            short-label="Dividir"
            icon="i-lucide-split"
            :size="controlSize"
            color="neutral"
            variant="outline"
            block
            class="h-full justify-center"
            title="Dividir a conta entre pessoas (abre no Pagamento)"
            :disabled="!items.length || loading || saving"
            data-pos-split
            @click="$emit('split')"
          />
          <OperatorButton
            v-else-if="cell === 'note' && activeItem"
            label="Observação"
            icon="i-lucide-message-square-text"
            :size="controlSize"
            color="neutral"
            variant="outline"
            block
            class="h-full justify-center"
            :disabled="mutationBusy"
            data-pos-line-note
            @click="chooseMode('note')"
          />
        </div>
      </template>
    </div>
  </DefineControlGrid>
  <DefineTicketBody>
      <!-- TOPO DA COMANDA (reorganização do dono, 10/10): só LEITURA, o que ela é (itens,
           linhas, o pé com a cozinha), e o gesto raro (Selecionar, Alt S), discreto e à
           vista. O que AGE na comanda inteira mora no pé, junto do Pagamento. -->
      <header
        v-if="!batchMode"
        class="shrink-0 border-b border-border"
        :class="sheet ? '' : 'h-16'"
        data-pos-ticket-header
      >
        <!-- A MESMA ALTURA da barra do topo da venda (h-16): as duas divisórias de baixo
             correm na mesma linha (dono, 10/10). Duas linhas: o que a comanda é (e o
             Selecionar) e o estado da cozinha dito em palavra. -->
        <div class="flex h-full flex-col justify-center gap-0.5 pr-2 pl-3.5" :class="sheet ? 'min-h-14 py-1.5' : ''">
          <div class="flex items-center gap-2">
            <div class="min-w-0 flex-1">
              <h3 v-if="sheet" class="op-title tnum [overflow-wrap:anywhere]" data-pos-sheet-title>{{ tabTitle ? `${tabTitle} · ` : "" }}{{ cartUnits }} {{ cartUnits === 1 ? "item" : "itens" }}</h3>
              <div v-else class="flex items-baseline gap-x-1.5 whitespace-nowrap">
                <h3 class="op-title tnum" data-pos-ticket-count>{{ cartUnits }} {{ cartUnits === 1 ? "item" : "itens" }}</h3>
                <span v-if="items.length" class="op-micro text-muted-foreground tnum">em {{ items.length }} {{ items.length === 1 ? "linha" : "linhas" }}</span>
              </div>
            </div>
            <NuxtButton
              ref="listEntry"
              :size="controlSize"
              color="neutral"
              variant="ghost"
              icon="i-lucide-list-checks"
              class="shrink-0"
              aria-keyshortcuts="Alt+s"
              title="Selecionar linhas (Alt S): transferir, descontar e remover várias"
              data-pos-select-lines
              @click="toggleBatchMode"
            >
              Selecionar
            </NuxtButton>
            <NuxtButton
              v-if="sheet"
              size="xl"
              color="neutral"
              variant="ghost"
              icon="i-lucide-chevron-down"
              square
              class="shrink-0"
              aria-label="Recolher a comanda"
              @click="sheetOpen = false"
            />
          </div>
          <!-- O estado da cozinha, numa linha discreta: o que falta, o que já foi e o
               envio automático (o ajuste mora em Ajustes › Envio à cozinha; o toque no
               texto leva lá). Na coluna estreita, o curto escrito à mão. -->
          <p v-if="fireBar.visible" class="flex items-center gap-x-1.5 op-micro whitespace-nowrap text-muted-foreground" data-pos-kitchen-state>
            <Icon name="lucide:chef-hat" class="size-3.5 shrink-0" aria-hidden="true" />
            <span v-if="kitchenStateText">{{ kitchenStateText }}</span>
            <template v-if="!sheet">
              <span v-if="kitchenStateText" aria-hidden="true">·</span>
              <NuxtButton
                color="neutral"
                variant="ghost"
                class="h-auto min-h-0 rounded-sm p-0 op-micro font-normal text-muted-foreground underline-offset-2 hover:bg-transparent hover:text-foreground hover:underline"
                :title="autoFire ? 'Envio automático ligado na estação destes itens (Ajustes › Envio à cozinha)' : 'Envio automático desligado (Ajustes › Envio à cozinha)'"
                :aria-label="`envio automático: ${autoFire ? 'ligado' : 'desligado'}`"
                data-pos-auto-fire
                :data-auto-fire="autoFire ? 'on' : 'off'"
                @click="$emit('autoFireSettings')"
              ><span class="hidden @min-[24rem]:inline">envio automático: {{ autoFire ? "ligado" : "desligado" }}</span><span class="@min-[24rem]:hidden">automático {{ autoFire ? "ligado" : "desligado" }}</span></NuxtButton>
            </template>
          </p>
        </div>
      </header>

      <!-- Modo seleção (Alt S): o cabeçalho diz o que está marcado, e só. As ações nas
           linhas marcadas moram no MESMO lugar das ações da linha (o bloco acima do
           pé), em grade, com rótulo: a faixa de cima não espreme ícones. -->
      <template v-else>
        <header class="flex shrink-0 items-center gap-2 border-b border-border bg-primary/10 px-2" :class="sheet ? 'min-h-14 py-1.5' : 'h-16'" data-pos-selection-bar>
          <NuxtButton
            :size="controlSize"
            color="neutral"
            variant="ghost"
            icon="i-lucide-x"
            square
            class="shrink-0"
            aria-label="Concluir seleção"
            title="Sair da seleção (Esc)"
            @click="toggleBatchMode"
          />
          <p class="min-w-0 flex-1 op-label font-semibold tnum">
            {{ selection.count ? `${selection.count} ${selection.count === 1 ? "selecionada" : "selecionadas"}` : "Toque nas linhas para marcar" }}
          </p>
        </header>
      </template>

      <div
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
            <NuxtButton
              v-if="batchMode"
              color="neutral"
              variant="ghost"
              class="w-11 shrink-0 justify-center rounded-none"
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
            </NuxtButton>
            <NuxtButton
              color="neutral"
              variant="ghost"
              class="grid min-h-12 min-w-0 flex-1 grid-cols-[2.25rem_minmax(0,1fr)_auto] items-center gap-x-2.5 rounded-none py-1.5 pr-3.5 text-left font-normal hover:bg-transparent focus-visible:outline-none"
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
                <!-- O nome da casa QUEBRA a linha, nunca corta (dono, 10/10). -->
                <span
                  class="block op-body leading-5 [overflow-wrap:anywhere]"
                  :class="activeLineId === item.line_id && editorVisible ? 'font-semibold' : 'font-medium'"
                  data-pos-line-name
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
            </NuxtButton>
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
              ><NuxtButton
                v-if="lineKitchenState(item) === 'fired_cancellable'"
                color="neutral"
                variant="ghost"
                :disabled="mutationBusy || firing || !unfireAction.enabled"
                :label="unfireAction.label"
                @click.stop="$emit('unfire', item.line_id)"
              />
              <div v-if="!batchMode && !lineAdjustmentsBlocked" class="mt-1 flex justify-between">
                <NuxtButton
                  color="primary"
                  variant="ghost"
                  icon="i-lucide-sticky-note"
                  label="Observação"
                  @click="
                    selectLine(item.line_id);
                    openNoteDialog();
                  "
                />
              </div>
            </div>
          </li>
        </ul>
      </div>

      <!-- O BLOCO DE AÇÃO (dono, 10/10): colado no pé da lista, borda primária em cima.
           Um lugar só para AGIR sobre linhas: a linha aberta no editor (↑↓, clique) ou
           as linhas marcadas na seleção. Cabeçalho (o que se edita e a dica do teclado
           do momento), uma divisória, e os controles em grade de duas colunas iguais.
           Desconto e observação abrem AQUI, no lugar da grade, e terminam em Cancelar
           ou Aplicar: nada de modal para ajuste de linha. -->
      <section
        v-if="editorVisible || batchMode"
        class="shrink-0 border-t-2 border-primary bg-card px-3 pt-2 shadow-[0_-10px_24px_rgb(0_0_0/.10)]"
        :class="batchMode ? 'pb-3' : 'pb-2'"
        aria-label="Console do item"
        data-pos-line-editor
      >
        <!-- TOQUE (v4 tablet b): um instrumento só. A caixa grande mostra o número; o
             numérico 3×4 escreve nele; a coluna à direita tem Desconto, Observação,
             Remover e Pronto. -->
        <template v-if="touchEditor && activeItem && lineEditing !== 'note'">
          <div class="flex items-center gap-3" data-pos-touch-editor>
            <p class="min-w-0 flex-1 truncate op-label text-muted-foreground">
              <template v-if="inDiscountMode">Desconto em <b class="font-semibold text-foreground">{{ activeItem.name }}</b></template>
              <template v-else-if="isWeighedLine(activeItem)">Peça pesada: para trocar, remova e lance a outra etiqueta.</template>
              <template v-else>Quantidade de <b class="font-semibold text-foreground">{{ activeItem.name }}</b> <span class="tnum">(era {{ qtyWas }})</span></template>
            </p>
            <output
              class="grid h-12 min-w-20 shrink-0 place-items-center rounded-md border-2 border-foreground/80 bg-card px-3 text-3xl font-semibold tnum"
              :aria-label="inDiscountMode ? 'Desconto' : `Quantidade de ${activeItem.name}`"
              data-pos-touch-editor-value
            >{{ touchEditorValue }}</output>
          </div>
          <p v-if="activeAuthorship || lineKitchenState(activeItem) === 'fired_cancellable'" class="mt-1 flex items-center gap-2 op-micro text-muted-foreground">
            <span class="min-w-0 flex-1 truncate">{{ activeAuthorship }}</span>
            <NuxtButton
              v-if="lineKitchenState(activeItem) === 'fired_cancellable'"
              color="primary"
              variant="ghost"
              class="shrink-0"
              :disabled="mutationBusy || firing || !unfireAction.enabled"
              :label="unfireAction.label"
              @click="$emit('unfire', activeItem.line_id)"
            />
          </p>
        </template>
        <!-- O CABEÇALHO do bloco: o que se edita (ou o que está marcado) e a dica do
             teclado do MOMENTO. A divisória separa a leitura dos controles. -->
        <template v-if="(lineControlsInGrid || lineEditing === 'note') && activeItem">
          <div class="flex items-start gap-2">
            <p class="min-w-0 flex-1 pt-1 op-label [overflow-wrap:anywhere]" data-pos-line-editor-title>
              <span class="text-muted-foreground">{{ lineEditing === "discount" ? "Desconto em " : lineEditing === "note" ? "Observação em " : "Editando " }}</span>
              <b class="font-semibold text-foreground">{{ activeItem.name }}</b>
              <span class="whitespace-nowrap text-muted-foreground tnum"> · {{ formatBRL(unitChargedQ(activeItem)) }}{{ isWeighedLine(activeItem) ? "/kg" : " cada" }}</span>
            </p>
            <NuxtButton
              color="neutral"
              variant="ghost"
              icon="i-lucide-x"
              square
              class="-mt-0.5 -mr-1 shrink-0"
              aria-label="Fechar o editor"
              aria-keyshortcuts="Escape"
              title="Fechar o editor (Esc)"
              data-pos-line-editor-close
              @click="closeEditor"
            />
          </div>
          <p
            v-if="!coarsePointer && !sheet"
            class="-mt-0.5 flex flex-wrap items-center gap-x-1.5 op-micro text-muted-foreground"
            data-pos-keyboard-hint
          >
            <template v-for="(part, index) in keyboardHint" :key="part">
              <span v-if="index" aria-hidden="true">·</span><span>{{ part }}</span>
            </template>
          </p>
          <div class="-mx-3 my-2 border-t border-border" aria-hidden="true" data-pos-editor-divider />
        </template>
        <template v-else-if="batchMode">
          <p class="op-micro text-muted-foreground" data-pos-batch-hint>
            {{ selection.count ? "Ações nas linhas marcadas" : "Marque as linhas na lista para agir em várias de uma vez" }}
          </p>
          <div class="-mx-3 my-2 border-t border-border" aria-hidden="true" data-pos-editor-divider />
        </template>

        <!-- OBSERVAÇÃO: escrita aqui mesmo (Enter aplica, Esc cancela). -->
        <div v-if="lineEditing === 'note' && noteDraft" class="grid grid-cols-2 gap-2" data-pos-note-panel>
          <NuxtTextarea
            ref="noteField"
            v-model="noteDraft.text"
            class="col-span-2"
            :rows="2"
            autoresize
            placeholder="Ex.: sem cebola, bem passado"
            aria-label="Observação da linha"
            data-pos-note-text
            @keydown="onNoteKeydown"
          />
          <p class="col-span-2 -mt-1 op-micro text-muted-foreground">A observação sai junto com o item para a cozinha.</p>
          <NuxtButton :size="controlSize" color="neutral" variant="outline" block class="justify-center" label="Cancelar" data-pos-edit-cancel @click="cancelNote" />
          <NuxtButton :size="controlSize" color="primary" block class="justify-center" label="Aplicar" data-pos-edit-apply @click="saveNote" />
        </div>

        <!-- DESCONTO (da linha ou das marcadas): o formato ocupa as duas colunas da
             grade, o valor dito por extenso, o numérico, o motivo, e Cancelar/Aplicar. -->
        <div v-else-if="lineEditing === 'discount'" class="grid grid-cols-2 gap-2" data-pos-discount-panel>
          <NuxtButton
            v-for="mode in discountModes"
            :key="mode.ref"
            :size="controlSize"
            color="neutral"
            variant="outline"
            active-color="primary"
            active-variant="solid"
            block
            class="justify-center"
            :active="numpadMode === mode.ref"
            :aria-pressed="numpadMode === mode.ref"
            :disabled="mutationBusy"
            :label="mode.label"
            @click="chooseMode(mode.ref)"
          />
          <p class="col-span-2 flex items-baseline justify-between gap-2 op-label text-muted-foreground" data-pos-discount-value>
            <span>{{
              selectMode
                ? `Desconto em ${selection.units} ${selection.units === 1 ? "item" : "itens"}`
                : numpadMode === "disc_brl"
                  ? "Desconto por unidade"
                  : "Desconto percentual"
            }}</span>
            <strong class="op-title text-foreground tnum">{{
              numpadMode === "disc_brl"
                ? `R$ ${numpadBuffer || "0"}`
                : `${numpadBuffer || "0"}%`
            }}</strong>
          </p>
            <div v-if="numpadVisible" class="col-span-2 grid grid-cols-3 gap-1.5" data-pos-line-numpad>
              <NuxtButton
                v-for="key in [1, 2, 3, 4, 5, 6, 7, 8, 9, 'decimal', 0, 'back']"
                :key="key"
                :color="key === 'back' ? 'error' : 'neutral'"
                variant="outline"
                class="justify-center op-title"
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
                :label="typeof key === 'number' ? String(key) : key === 'back' ? '⌫' : ','"
                @click="
                  typeof key === 'number'
                    ? onDigit(String(key))
                    : key === 'back'
                      ? onBackspace()
                      : onComma()
                "
              />
            </div>
          <NuxtSelect
            :model-value="discountReason || undefined"
            :items="reasonOptions.map((reason) => ({ label: reason.label, value: reason.ref }))"
            aria-label="Motivo do desconto"
            :disabled="mutationBusy"
            class="col-span-2 w-full"
            data-pos-discount-reason
            @update:model-value="(value) => { discountReason = String(value ?? ''); if (!discountDraft) commitDiscount(); }"
          />
          <template v-if="discountDraft">
            <NuxtButton :size="controlSize" color="neutral" variant="outline" block class="justify-center" label="Cancelar" data-pos-edit-cancel @click="cancelDiscount" />
            <NuxtButton :size="controlSize" color="primary" block class="justify-center" label="Aplicar" :disabled="mutationBusy || !discountTargets.length" data-pos-edit-apply @click="applyDiscount" />
          </template>
        </div>

        <!-- A GRADE da linha aberta (quantidade | Remover; Desconto | Observação). -->
        <ReuseControlGrid v-else-if="lineControlsInGrid && activeItem" :rows="lineRows" block="line" />

        <!-- A GRADE das marcadas (Transferir | Desconto; Remover | Enviar…). -->
        <div v-else-if="batchMode && selection.count" class="grid grid-cols-2 gap-2" data-pos-batch-actions>
          <template v-for="(row, rowIndex) in batchRows" :key="rowIndex">
            <div
              v-for="cell in row"
              :key="cell"
              class="op-fit-scope min-w-0"
              :class="row.length === 1 ? 'col-span-2' : ''"
              :data-pos-batch-cell="cell"
            >
              <OperatorButton
                v-if="cell === 'move'"
                label="Transferir"
                icon="i-lucide-split"
                :size="controlSize"
                color="neutral"
                variant="outline"
                block
                class="h-full justify-center"
                :shortcut="coarsePointer ? undefined : 'F10'"
                :disabled="loading"
                title="Transferir as linhas marcadas para outra comanda (F10)"
                @click="$emit('move', selection.lineIds)"
              />
              <OperatorButton
                v-else-if="cell === 'discount'"
                label="Desconto"
                icon="i-lucide-percent"
                :size="controlSize"
                color="neutral"
                variant="outline"
                block
                class="h-full justify-center"
                :disabled="!selection.count"
                title="Desconto nas linhas marcadas"
                @click="toggleDiscount"
              />
              <OperatorButton
                v-else-if="cell === 'remove'"
                label="Remover"
                icon="i-lucide-trash-2"
                :size="controlSize"
                color="error"
                variant="outline"
                block
                class="h-full justify-center bg-default font-semibold"
                :disabled="mutationBusy || !selection.count"
                title="Remover as linhas marcadas"
                @click="batchRemove"
              />
              <OperatorButton
                v-else-if="cell === 'fire'"
                label="Enviar à cozinha"
                short-label="Enviar"
                icon="i-lucide-chef-hat"
                :size="controlSize"
                color="primary"
                variant="outline"
                block
                class="h-full justify-center bg-default font-semibold"
                :disabled="mutationBusy || firing || !fireAction.enabled"
                title="Enviar à cozinha só as marcadas"
                data-pos-batch-fire
                @click="batchFire"
              />
              <OperatorButton
                v-else-if="cell === 'unfire'"
                :label="unfireAction.label || 'Cancelar envio à cozinha'"
                short-label="Cancelar envio"
                icon="i-lucide-undo-2"
                :size="controlSize"
                color="neutral"
                variant="outline"
                block
                class="h-full justify-center"
                :disabled="mutationBusy || firing || !unfireAction.enabled"
                @click="batchUnfire"
              />
            </div>
          </template>
        </div>

        <p
          v-if="lineControlsInGrid && activeItem && !lineEditing && (activeAuthorship || lineKitchenState(activeItem) === 'fired_cancellable')"
          class="mt-1.5 flex flex-wrap items-center gap-x-2 op-micro text-muted-foreground"
          data-pos-line-authorship
        >
          <span class="min-w-0 flex-1">{{ activeAuthorship }}</span>
          <NuxtButton
            v-if="lineKitchenState(activeItem) === 'fired_cancellable'"
            color="primary"
            variant="ghost"
            class="shrink-0"
            :disabled="mutationBusy || firing || !unfireAction.enabled"
            :label="unfireAction.label"
            @click="$emit('unfire', activeItem.line_id)"
          />
        </p>

        <div v-if="touchEditor && activeItem && lineEditing !== 'note'" class="mt-2 grid grid-cols-[repeat(3,minmax(0,1fr))_minmax(0,1.6fr)] gap-2" data-pos-line-numpad>
          <template v-for="(row, rowIndex) in [[1, 2, 3], [4, 5, 6], [7, 8, 9], ['decimal', 0, 'back']]" :key="rowIndex">
            <!-- O numérico do toque é xl com a altura de tecla (h-14/h-16): a mesma
                 exceção de altura do numérico do Pagamento, alvo de polegar. -->
            <NuxtButton
              v-for="key in row"
              :key="String(key)"
              size="xl"
              color="neutral"
              variant="outline"
              class="h-14 justify-center text-3xl font-medium tnum sm:h-16"
              :icon="key === 'back' ? 'i-lucide-delete' : undefined"
              :aria-label="typeof key === 'number' ? 'Dígito ' + key : key === 'back' ? 'Apagar último dígito' : 'Vírgula'"
              :disabled="mutationBusy || !numpadCanType || (key === 'decimal' && numpadMode !== 'disc_brl')"
              :label="key === 'back' ? undefined : key === 'decimal' ? ',' : String(key)"
              @click="typeof key === 'number' ? onDigit(String(key)) : key === 'back' ? onBackspace() : onComma()"
            />
            <NuxtButton
              v-if="rowIndex === 0"
              size="xl"
              color="neutral"
              variant="outline"
              active-color="primary"
              active-variant="solid"
              :active="discountOpen"
              icon="i-lucide-percent"
              class="h-14 justify-center gap-1.5 px-1.5 text-sm font-semibold sm:h-16"
              :ui="SIDE_KEY_UI"
              :aria-pressed="discountOpen"
              :disabled="mutationBusy || lineAdjustmentsBlocked"
              :label="discountOpen ? 'Quantidade' : 'Desconto'"
              data-pos-line-discount
              @click="toggleDiscount"
            />
            <NuxtButton
              v-else-if="rowIndex === 1"
              size="xl"
              color="neutral"
              variant="outline"
              icon="i-lucide-message-square-text"
              class="h-14 justify-center gap-1.5 px-1.5 text-sm font-semibold sm:h-16"
              :ui="SIDE_KEY_UI"
              :disabled="mutationBusy || lineAdjustmentsBlocked"
              label="Observação"
              @click="chooseMode('note')"
            />
            <NuxtButton
              v-else-if="rowIndex === 2"
              size="xl"
              color="error"
              variant="outline"
              icon="i-lucide-trash-2"
              class="h-14 justify-center gap-1.5 px-1.5 text-sm font-semibold sm:h-16"
              :ui="SIDE_KEY_UI"
              :disabled="mutationBusy"
              label="Remover"
              @click="askRemove(activeItem.line_id)"
            />
            <NuxtButton
              v-else
              size="xl"
              color="neutral"
              icon="i-lucide-check"
              class="h-14 justify-center gap-1.5 px-1.5 text-sm font-semibold sm:h-16"
              :ui="SIDE_KEY_UI"
              data-pos-line-editor-close
              @click="closeEditor"
            >Pronto</NuxtButton>
          </template>
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


      <!-- Pé: UMA faixa, o maior alvo da tela (Pagamento F4 com o total dentro). Na
           seleção, o pé encolhe para o total: o gesto geral espera o Concluir. -->
      <div v-if="batchMode" class="flex shrink-0 items-baseline justify-between border-t border-border px-3.5 py-3">
        <span class="op-label text-muted-foreground">Total parcial</span>
        <strong v-if="totalConfirmed" class="text-xl font-semibold tnum" data-pos-batch-total>{{ totalText }}</strong>
        <span v-else-if="totalShown" class="op-label text-muted-foreground" data-pos-batch-total :data-total-state="total.status">{{ totalText }}</span>
      </div>
      <!-- FOLHA ABERTA (v4 tablet b): pagar direto daqui, pelos meios eletrônicos que
           o dispositivo leva à mesa. "Outras formas" abre o Pagamento de sempre. -->
      <div v-else-if="sheet && quickPayments?.length && !primaryLabel" class="shrink-0 border-t border-border p-3" data-pos-sheet-pay>
        <div class="mb-2 flex items-baseline gap-2">
          <span class="op-label text-muted-foreground">Pagar</span>
          <strong v-if="totalConfirmed" class="text-3xl font-semibold tnum" data-pos-sheet-pay-total>{{ totalText }}</strong>
          <span v-else class="op-title font-normal text-muted-foreground" data-pos-sheet-pay-total :data-total-state="total.status">{{ totalText }}</span>
          <span class="flex-1" />
          <NuxtButton
            size="xl"
            color="primary"
            variant="ghost"
            :disabled="!items.length || loading || saving"
            label="Outras formas"
            data-pos-sheet-other-payment
            @click="$emit('prepare')"
          />
        </div>
        <div class="grid gap-2" :class="primaryQuickPayments.length > 1 ? 'grid-cols-2' : 'grid-cols-1'">
          <NuxtButton
            v-for="method in primaryQuickPayments"
            :key="method.ref"
            size="xl"
            color="primary"
            class="h-14 justify-center gap-2.5 text-lg font-semibold"
            :disabled="!items.length || loading || saving"
            :data-pos-sheet-pay-method="method.ref"
            @click="$emit('pay', method.ref)"
          >
            <Icon :name="method.icon" class="size-6 shrink-0" />
            {{ method.label }}
          </NuxtButton>
          <!-- V6-CAIXA: dinheiro na mesa, secundário; a gaveta do Balcão abre pelo
               cartão que a venda deixa (nunca sozinha longe dela). -->
          <NuxtButton
            v-for="method in secondaryQuickPayments"
            :key="method.ref"
            size="xl"
            color="neutral"
            variant="outline"
            class="col-span-full h-12 justify-center gap-2.5 font-semibold"
            :disabled="!items.length || loading || saving"
            :data-pos-sheet-pay-method="method.ref"
            @click="$emit('pay', method.ref)"
          >
            <Icon :name="method.icon" class="size-5 shrink-0" />
            {{ method.label }}
            <span v-if="method.hint" class="font-normal text-muted-foreground">· {{ method.hint }}</span>
          </NuxtButton>
        </div>
      </div>
      <div
        v-else
        class="grid shrink-0 gap-2.5 px-3 pb-3"
        :class="editorVisible ? 'pt-0' : 'border-t border-border pt-3'"
        data-pos-ticket-foot
      >
        <!-- O bloco da COMANDA, sempre aqui, logo acima do Pagamento (não pula quando o
             editor abre ou fecha). Com o editor aberto, ele continua a grade de cima,
             sem divisória: é o mesmo conjunto de controles. -->
        <ReuseControlGrid v-if="tabRows.length" :rows="tabRows" block="tab" />
        <!-- PAGAMENTO (dono, 10/10, refeito): uma linha só. À esquerda o gesto (ícone,
             rótulo, F4 discreto); à direita o total, grande, sem rótulo empilhado em
             cima. O TOTAL NUNCA CORTA: ele não encolhe; quem cede é o rótulo (vira o
             ícone) e a tecla. Sem conexão, o número vem com "total sem conexão" ao
             lado, na mesma linha (#1635). -->
        <NuxtButton
          size="xl"
          color="primary"
          block
          class="h-14 justify-between gap-3 px-4"
          :disabled="!items.length || loading || saving"
          :aria-busy="loading || undefined"
          aria-keyshortcuts="F4"
          :title="`${primaryText} (F4)`"
          data-pos-primary
          @click="$emit('prepare')"
        >
          <span class="flex min-w-0 items-center gap-2.5">
            <Icon :name="loading ? 'lucide:loader-circle' : primaryIconName" class="size-5 shrink-0" :class="loading ? 'animate-spin motion-reduce:animate-none' : ''" />
            <span class="text-lg font-semibold whitespace-nowrap" data-pos-primary-label>{{ primaryText }}</span>
            <OperatorKbd v-if="!coarsePointer" variant="inverse" class="hidden opacity-80 @min-[24rem]:inline-flex" aria-hidden="true">F4</OperatorKbd>
          </span>
          <span v-if="totalShown" class="flex shrink-0 items-baseline gap-2" data-pos-primary-total :data-total-state="total.status">
            <span v-if="total.status === 'offline'" class="op-micro font-medium whitespace-nowrap opacity-90">total sem conexão</span>
            <span v-if="totalConfirmed" class="text-xl font-semibold whitespace-nowrap tnum @min-[24rem]:text-3xl" data-pos-primary-total-value>{{ totalText }}</span>
            <span v-else class="op-body font-medium whitespace-nowrap opacity-90">{{ totalText }}</span>
          </span>
        </NuxtButton>
      </div>
  </DefineTicketBody>

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
    <NuxtButton size="xl" color="primary" class="justify-self-center" :disabled="loading" label="Escolher comanda" @click="$emit('requestTab')" />
  </div>

  <!-- FOLHA (v4 tablet, `pos-tablet.jpg`): abaixo do desktop a comanda é a barra da
       ação do momento na base (`OperatorActionBar`, em fluxo, acima da barra
       inferior) e, puxada, a gaveta de baixo do kit (`NuxtDrawer`), com as linhas, o
       editor e o numérico. O véu é o da gaveta, ATRÁS dela: a folha nunca escurece a
       si mesma. -->
  <template v-else-if="sheet">
    <OperatorActionBar
      label="Comanda"
      :context-label="sheetContextLabel"
      :context-value="totalConfirmed ? totalText : ''"
      :action="sheetAction"
      :secondary="sheetSecondary"
      :data-pos-sheet="sheetOpen ? 'open' : 'closed'"
      :data-total-state="total.status"
      data-pos-sheet-bar
    />
    <NuxtDrawer
      v-model:open="sheetOpen"
      :title="sheetTitle"
      description="As linhas da comanda, o editor do item e o pagamento"
      data-pos-sheet-drawer
    >
      <template #content>
        <div
          class="@container flex max-h-[85dvh] min-h-0 flex-col bg-card text-card-foreground"
          data-pos-ticket
          data-pos-sheet="open"
        >
          <ReuseTicketBody />
        </div>
      </template>
    </NuxtDrawer>
  </template>


  <!-- COMPOSIÇÃO (v4, `pos-sale4.html`): a comanda é lista + total + Pagamento, e só.
       O editor da linha aparece sob demanda, colado no pé da lista; o numérico da
       tela só no desconto e nos dispositivos de toque (no balcão o teclado físico
       digita a quantidade). -->
  <div
    v-else
    class="@container relative flex min-h-0 flex-col overflow-hidden bg-card text-card-foreground md:h-full"
    data-pos-ticket
  >
    <ReuseTicketBody />
  </div>

  <NuxtModal
    :open="!!confirmAction"
    :title="confirmTitle"
    :ui="{ content: 'sm:max-w-sm' }"
    data-pos-confirm-remove
    @update:open="(value: boolean) => { if (!value) cancelConfirm(); }"
  >
    <template #description>
      <template v-if="confirmAction?.kind === 'line' && confirmAction.fired">
        <strong>{{ confirmAction.name }}</strong> já foi enviado à cozinha.
        Remover tira a linha do pedido; avise o preparo se necessário.
      </template>
      <template v-else-if="confirmAction?.kind === 'line'">
        A linha sai do pedido. Dá para desfazer logo depois.
      </template>
      <template v-else-if="confirmAction?.kind === 'batch'">
        {{
          confirmAction.hasFired
            ? "As linhas selecionadas saem do pedido, inclusive as que já foram à cozinha."
            : "As linhas selecionadas saem do pedido."
        }}
      </template>
    </template>
    <template #footer>
      <div class="flex w-full flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <NuxtButton color="neutral" variant="outline" label="Cancelar" @click="cancelConfirm" />
        <NuxtButton color="error" :label="confirmCta" @click="runConfirm" />
      </div>
    </template>
  </NuxtModal>

  <PosKitchenTicketDialog
    :open="kitchenLine != null"
    :line-name="kitchenLine?.name ?? ''"
    :tickets="kitchenLine?.kitchen_tickets ?? []"
    @update:open="(value) => { if (!value) kitchenLineId = ''; }"
  />
</template>
