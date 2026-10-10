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
import { fireCellView, kitchenStateView, markedSummary, markRange, toggleMark as toggleMarkRule } from "~/presentation/ticketColumn";
import { firedLineIncrease, firedLineShrinkPolicy, offersResendWithNote } from "~/presentation/firedLineChange";

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
  /** Os SKUs que vão sozinhos (estação com envio automático): a linha diz "vai sozinho". */
  autoFireSkus?: string[];
  /**
   * O PDV está sem conexão (a venda de balcão segue). O que precisa do servidor fica
   * apagado com o motivo em palavra, nunca escondido: enviar, desconto, transferir,
   * juntar, liberar e cancelar envio.
   */
  offline?: boolean;
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
  /** Transferir: com linhas marcadas (ou "Transferir esta") o diálogo nasce com elas;
   *  `mode` é a porta do menu da comanda ("Juntar com outra comanda"). */
  move: [lineIds?: string[], mode?: "transfer" | "merge"];
  /** + numa linha que já está na cozinha: as unidades novas vão numa linha nova, a
   *  enviar. `done` devolve o line_id dela, para o editor seguir a linha nova. */
  addLike: [lineId: string, qty: number, done: (lineId: string) => void];
  /** "Reenviar com a observação": cancela na cozinha e envia de novo esta linha. */
  resend: [lineId: string];
  /** "Liberar comanda" do menu da comanda (a confirmação mora no cabeçalho da venda). */
  release: [];
  /** Há rascunho aberto (desconto, observação) ou linhas marcadas: o envio automático espera. */
  autoFireHold: [held: boolean];
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

// MARCAR SEM MODO (decisão 1 do dono, 10/10): a caixa de marcar está sempre à mão (no
// hover e no foco da linha; visível em todas assim que há marcadas). A linha aberta é a
// primeira marcada: marcar outra transforma o bloco de 1 no bloco de N, nas mesmas
// posições, e desmarcar até sobrar uma volta ao editor dela (`presentation/ticketColumn`).
// A seleção é um conjunto de `line_id`s, a mesma chave que fire/unfire mandam ao servidor.
const selected = ref<Set<string>>(new Set());
const selection = computed(() => selectionView(props.items, selected.value));
const marked = computed(() => markedSummary(props.items, selected.value));
// O cabeçalho da comanda conta ITENS, não linhas — a mesma grandeza da cozinha,
// do resumo do pagamento, do quadro de comandas e da tela virada para o
// cliente. Era o último lugar do app que ainda falava linha, e o mais lido.
const cartUnits = computed(() => countUnits(props.items));
/** O bloco de N: duas ou mais linhas marcadas. */
const selectMode = computed(() => selection.value.count >= 2);
function isSelected(lineId: string) {
  return selected.value.has(lineId);
}
const markAnchor = ref("");
function applyMark(result: { marked: Set<string>; open: string }) {
  const wasPlural = selectMode.value;
  selected.value = result.marked;
  if (result.open) {
    selectLine(result.open);
  }
  if (wasPlural !== selectMode.value) {
    // Trocar de objeto fecha o rascunho que era do outro.
    discountOpen.value = false;
    noteDraft.value = null;
    numpadMode.value = "qty";
    syncBufferToMode();
  }
}
/** A linha aberta no editor (a que entra na conta ao marcar a primeira outra). */
const openLineForMarks = computed(() => (editorVisible.value || selectMode.value ? activeLineId.value : ""));
function toggleSelect(lineId: string, range = false) {
  const anchor = markAnchor.value && (selectMode.value || markAnchor.value === openLineForMarks.value) ? markAnchor.value : openLineForMarks.value;
  if (range && anchor) {
    applyMark(markRange(props.items, selected.value, anchor, lineId));
  } else {
    applyMark(toggleMarkRule(selected.value, lineId, selectMode.value ? "" : openLineForMarks.value));
  }
  markAnchor.value = lineId;
}
function clearSelection() {
  selected.value = new Set();
}
/** Esc ou "Desmarcar": volta ao editor da linha em foco, sem marcas. */
function unmarkAll() {
  const keep = activeLineId.value;
  clearSelection();
  discountOpen.value = false;
  noteDraft.value = null;
  numpadMode.value = "qty";
  if (keep) selectLine(keep);
}
// Keep the selection consistent when the cart changes (removed lines drop out).
watch(
  () => props.items.map((item) => item.line_id).join("|"),
  () => {
    const pruned = pruneSelection(selected.value, props.items);
    if (pruned.size === 1) applyMark({ marked: new Set(), open: [...pruned][0]! });
    else selected.value = pruned;
  },
);
/** Clique na linha ABRE a linha. Com marcadas (o foco é o bloco de N), o clique marca ou
 *  desmarca, para um clique distraído não jogar fora as marcas; Shift + clique marca o
 *  intervalo. O toque longo já marcou: o clique que o segue não faz nada. */
// O foco por teclado (Tab) abre a linha; o foco que vem de um clique espera o clique,
// que decide entre abrir e marcar.
let rowPointer = false;
function onRowFocus(lineId: string) {
  if (rowPointer) return;
  if (!selectMode.value) selectLine(lineId);
}
function onRowClick(lineId: string, event: MouseEvent) {
  rowPointer = false;
  if (pressMarked.value) {
    pressMarked.value = false;
    return;
  }
  if (event.shiftKey || selectMode.value) {
    toggleSelect(lineId, event.shiftKey);
    return;
  }
  selectLine(lineId);
}
// Toque longo marca (tablet e celular): o toque curto continua abrindo a linha.
let pressTimer: ReturnType<typeof setTimeout> | null = null;
const pressMarked = ref(false);
function startPress(lineId: string, event: PointerEvent) {
  rowPointer = true;
  if (event.pointerType === "mouse") return;
  pressMarked.value = false;
  pressTimer = setTimeout(() => {
    pressMarked.value = true;
    toggleSelect(lineId);
  }, 500);
}
function endPress() {
  if (pressTimer) clearTimeout(pressTimer);
  pressTimer = null;
}
// O ENVIO AUTOMÁTICO ESPERA o rascunho e as marcas: ninguém quer a linha indo à cozinha
// no meio da observação que está sendo escrita.
const batchPending = ref(false);
// ATO EM LOTE CONCLUÍDO LIMPA AS MARCAS (regra única do estudo); no erro, ficam.
function completeBatch(success: boolean) {
  batchPending.value = false;
  if (success) clearSelection();
}
function batchFire() {
  if (
    props.loading ||
    props.saving ||
    props.firing ||
    props.offline ||
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
    props.offline ||
    batchPending.value ||
    !props.unfireAction.present ||
    !props.unfireAction.enabled
  )
    return;
  if (!selection.value.canUnfire) return;
  batchPending.value = true;
  emit("unfireLines", selection.value.lineIds, completeBatch);
}
// Remover o LOTE confirma e oferece Desfazer, como remover uma (uma regra só para
// destruir, 1 ou N): a seleção pode ter linha já enviada e o operador pode ter marcado a mais.
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
// O primeiro botão do pé segue o foco: com marcadas, "Enviar 3 marcadas" (e o F9 também).
const fireCell = computed(() =>
  fireCellView({
    unfired: fireBar.value.unfired,
    label: fireBar.value.label,
    disabled: fireBar.value.disabled,
    markedLines: selectMode.value ? selection.value.count : 0,
    markedFirable: selectMode.value ? selection.value.firableLineIds.length : 0,
    offline: Boolean(props.offline),
  }),
);
function onFireCell() {
  if (fireCell.value.onlyMarked) batchFire();
  else emit("fire");
}
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
type ControlCell = "qty" | "move" | "remove" | "fire" | "discount" | "split" | "note";
const lineControlsInGrid = computed(() => Boolean(activeItem.value) && editorVisible.value && !touchEditor.value);
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
  if (selectMode.value) return ["Espaço marca", "Shift clique marca o intervalo", "Esc desmarca tudo"];
  return ["Digite a quantidade", "Del remove", "↑↓ troca a linha"];
});
// O BLOCO DE N, nas MESMAS posições do bloco de 1 (posição fixa por verbo): só o canto
// da Quantidade (que é de uma linha) dá lugar a Transferir. Remover no alto à direita,
// Desconto e Observação embaixo.
const batchRows = computed<ControlCell[][]>(() => {
  const top: ControlCell[] = canMove.value && props.hasOpenTab ? ["move", "remove"] : ["remove"];
  return lineAdjustmentsBlocked.value ? [top] : [top, ["discount", "note"]];
});
const tabRows = computed<ControlCell[][]>(() => {
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
  label: fireCell.value.label,
  shortLabel: fireCell.value.shortLabel,
  icon: props.firing ? undefined : "i-lucide-chef-hat",
}));
const fireReserve = computed(() => (fireCell.value.count ? COUNT_RESERVE_REM : 0));
const kitchenState = computed(() =>
  kitchenStateView({
    unfired: fireBar.value.unfired,
    fired: fireBar.value.fired,
    autoFire: Boolean(props.autoFire),
    offline: Boolean(props.offline),
  }),
);
const kitchenStateText = computed(() => kitchenState.value.counts);
const autoFireSkuSet = computed(() => new Set(props.autoFireSkus || []));

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
const editorVisible = computed(() => Boolean(activeItem.value) && !selectMode.value && !editorClosed.value);
/** O bloco de ação existe: uma linha aberta ou várias marcadas. */
const blockVisible = computed(() => editorVisible.value || selectMode.value);
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
  if (mutationBusy.value || lineAdjustmentsBlocked.value || props.offline) return;
  noteDraft.value = null;
  discountOpen.value = !discountOpen.value;
  const fixed = !selectMode.value && activeItem.value?.discount?.type === "fixed";
  if (discountOpen.value) setMode(fixed ? "disc_brl" : "disc");
  else setMode("qty");
}
// EDITAR UMA LINHA É SEMPRE NO MESMO LUGAR (dono, 10/10): o desconto e a observação
// abrem no bloco, no lugar da grade, e terminam em Cancelar ou Aplicar. O desconto é um
// RASCUNHO na mesa E no toque: o número e o motivo só valem no Aplicar (Enter, ou o
// Aplicar do numérico do toque); Cancelar (Esc) devolve a linha como estava.
const discountDraft = computed(() => true);
function applyDiscount() {
  const wasBatch = selectMode.value;
  commitDiscount();
  discountOpen.value = false;
  setMode("qty");
  if (wasBatch) unmarkAll();
}
function cancelDiscount() {
  discountOpen.value = false;
  setMode("qty");
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
  if (selectMode.value) return discountOpen.value && !lineAdjustmentsBlocked.value;
  if (!editorVisible.value) return false;
  // No toque o numérico mora DENTRO do editor (um instrumento só, v4 tablet b).
  if (touchEditor.value) return false;
  return discountOpen.value;
});
/** O editor de toque (v4 `pos-tablet.jpg` b): "Quantidade de X (era 1)", a caixa
 *  grande, o numérico 3×4 de 64 px e a coluna Desconto · Observação · Remover ·
 *  Pronto. Um instrumento só para a quantidade, sem −/+ duplicado. */
const touchEditor = computed(() => coarsePointer.value && editorVisible.value);
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
// O dado já existia (POSCartItem.notes, intent, KDS). Nas marcadas, a mesma observação
// vai para todas ("para viagem", "sem glúten"); o rascunho nasce com a que elas já
// dividem, ou vazio quando cada uma tem a sua.
const noteDraft = ref<{ lineIds: string[]; text: string } | null>(null);
const noteField = ref<{ textareaRef?: HTMLTextAreaElement; $el?: HTMLElement } | null>(null);
function openNoteDialog() {
  if (lineAdjustmentsBlocked.value) return;
  discountOpen.value = false;
  setMode("qty");
  if (selectMode.value) {
    const chosen = props.items.filter((item) => selected.value.has(item.line_id));
    const notes = new Set(chosen.map((item) => (item.notes || "").trim()));
    noteDraft.value = { lineIds: chosen.map((item) => item.line_id), text: notes.size === 1 ? [...notes][0]! : "" };
  } else {
    const item = activeItem.value;
    if (!item) return;
    editorClosed.value = false;
    noteDraft.value = { lineIds: [item.line_id], text: item.notes || "" };
  }
  void nextTick(() => {
    const field = noteField.value?.textareaRef || noteField.value?.$el?.querySelector?.("textarea");
    field?.focus();
  });
}
// "Reenviar com a observação" (a linha já na cozinha, que ainda pode cancelar).
const resendOffer = ref("");
function saveNote() {
  const draft = noteDraft.value;
  noteDraft.value = null;
  if (!draft) return;
  const text = draft.text.trim();
  const single = draft.lineIds.length === 1 ? props.items.find((item) => item.line_id === draft.lineIds[0]) : null;
  draft.lineIds.forEach((lineId) => emit("setNotes", lineId, text));
  if (single && offersResendWithNote({
    fired: Boolean(single.fired),
    cancellable: lineKitchenState(single) === "fired_cancellable" && props.unfireAction.enabled,
    before: single.notes || "",
    after: text,
  })) {
    resendOffer.value = single.line_id;
  }
  if (draft.lineIds.length > 1) unmarkAll();
}
function resendWithNote() {
  const lineId = resendOffer.value;
  resendOffer.value = "";
  if (lineId) emit("resend", lineId);
}
watch(activeLineId, (lineId) => {
  if (resendOffer.value && resendOffer.value !== lineId) resendOffer.value = "";
});
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
  const draft = noteDraft.value;
  if (draft && draft.lineIds.length === 1 && draft.lineIds[0] !== activeLineId.value) noteDraft.value = null;
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
    // N como 1: confirma E oferece Desfazer (devolve cada linha como estava).
    const snapshots = action.lineIds
      .map((lineId) => props.items.find((entry) => entry.line_id === lineId))
      .filter((item): item is POSCartItem => Boolean(item))
      .map((item) => ({ ...item }));
    clearSelection();
    selectedLineId.value = "";
    snapshots.forEach((item) => emit("remove", item.line_id));
    toast(`${action.units} ${action.units === 1 ? "item removido" : "itens removidos"}.`, {
      action: { label: "Desfazer", onClick: () => snapshots.forEach((item) => emit("restore", item)) },
    });
    return;
  }
  const item = props.items.find((entry) => entry.line_id === action.lineId);
  if (item) removeWithUndo(item);
}

// ── As portas do raro (o ⋯ único da suíte, `OperatorMoreMenu`) ──────────────────────
// "Ações da comanda" no cabeçalho: o que age na comanda INTEIRA sem marcar nada
// (Transferir itens, Juntar com outra comanda, Liberar). Sem conexão, apagado com o motivo
// escrito sob o rótulo (o toque não tem dica de ponteiro).
const OFFLINE_REASON = "Volta com a conexão.";
type MoreItem = Record<string, unknown>;
const tabMenuItems = computed<MoreItem[][]>(() => {
  const offline = Boolean(props.offline);
  const reason = offline ? OFFLINE_REASON : undefined;
  const groups: MoreItem[][] = [];
  if (canMove.value) {
    groups.push([
      {
        label: "Transferir itens",
        icon: "i-lucide-arrow-right-left",
        kbds: coarsePointer.value ? undefined : ["F10"],
        disabled: offline || !props.items.length || props.loading,
        reason,
        onSelect: () => emit("move", selectMode.value ? selection.value.lineIds : undefined, "transfer"),
      },
      {
        label: "Juntar com outra comanda",
        icon: "i-lucide-merge",
        disabled: offline || !props.items.length || props.loading,
        reason,
        onSelect: () => emit("move", undefined, "merge"),
      },
    ]);
  }
  groups.push([{
    label: "Liberar comanda",
    icon: "i-lucide-x",
    color: "error",
    disabled: offline || props.loading,
    reason,
    onSelect: () => emit("release"),
  }]);
  return groups;
});
const showTabMenu = computed(() => props.hasOpenTab && !props.primaryLabel);
// O ⋯ do bloco de 1: o raro da linha aberta (dois toques), longe da grade de um toque.
const lineMenuItems = computed<MoreItem[]>(() => {
  const item = activeItem.value;
  if (!item) return [];
  const offline = Boolean(props.offline);
  const reason = offline ? OFFLINE_REASON : undefined;
  const state = lineKitchenState(item);
  const acts: MoreItem[] = [];
  if (canMove.value && props.hasOpenTab) {
    acts.push({
      label: "Transferir esta linha",
      icon: "i-lucide-arrow-right-left",
      disabled: offline || props.loading,
      reason,
      onSelect: () => emit("move", [item.line_id], "transfer"),
    });
  }
  if (state === "unfired" && fireBar.value.visible) {
    acts.push({
      label: "Enviar só esta à cozinha",
      icon: "i-lucide-chef-hat",
      disabled: offline || props.firing || !props.fireAction.enabled,
      reason,
      onSelect: () => emit("fireLines", [item.line_id], () => {}),
    });
  }
  if (state === "fired_cancellable") {
    acts.push({
      label: props.unfireAction.label || "Cancelar envio à cozinha",
      icon: "i-lucide-undo-2",
      disabled: offline || props.firing || !props.unfireAction.enabled,
      reason,
      onSelect: () => emit("unfire", item.line_id),
    });
  }
  if (hasKitchenCard(item)) {
    acts.push({ label: "Ver na cozinha", icon: "i-lucide-chef-hat", onSelect: () => { kitchenLineId.value = item.line_id; } });
  }
  if (acts.length && activeAuthorship.value) acts.unshift({ type: "label", label: activeAuthorship.value });
  return acts;
});
// O ⋯ do bloco de N: o raro das marcadas.
const batchMenuItems = computed<MoreItem[]>(() => {
  if (!selection.value.canUnfire || !props.unfireAction.present) return [];
  return [{
    label: "Cancelar envio das marcadas",
    icon: "i-lucide-undo-2",
    disabled: Boolean(props.offline) || props.firing || !props.unfireAction.enabled,
    reason: props.offline ? OFFLINE_REASON : undefined,
    onSelect: () => batchUnfire(),
  }];
});

function commitQty() {
  if (props.loading || props.saving) return;
  const lineId = activeLineId.value;
  if (!lineId) return;
  const next = clampQty(numpadBuffer.value, MAX_QTY);
  if (next <= 0) {
    askRemove(lineId);
    return;
  }
  const item = props.items.find((entry) => entry.line_id === lineId);
  const extra = item ? firedLineIncrease(item, next) : 0;
  if (extra) {
    addLike(lineId, extra);
    return;
  }
  if (item?.fired && next < item.qty && firedLineShrinkPolicy() === "ask") {
    // Pergunta 5 (pendente): a decisão do dono pluga aqui. Hoje só avisa (o selo da linha).
  }
  emit("setQty", lineId, next);
}
/** MAIS numa linha que já está na cozinha vai numa linha NOVA, a enviar; o editor segue
 *  a linha nova (é nela que o próximo + e o próximo dígito vão). */
function addLike(lineId: string, qty: number) {
  emit("addLike", lineId, qty, (newLineId: string) => {
    if (newLineId) selectLine(newLineId);
  });
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
/** Desconto em R$ é por unidade: na peça pesada seria "por quilo". Vale para a linha
 *  aberta e para o lote (com uma peça pesada entre as marcadas, só %). */
const fixedDiscountBlocked = computed(() =>
  selectMode.value ? marked.value.hasWeighed : Boolean(activeItem.value && isWeighedLine(activeItem.value)),
);
const numpadCanType = computed(() => {
  // Sem desconto de item, a seleção múltipla não tem o que digitar.
  if (lineAdjustmentsBlocked.value && (selectMode.value || inDiscountMode.value)) return false;
  const weighedActive = !!activeItem.value && isWeighedLine(activeItem.value);
  if (!inDiscountMode.value) return !!activeLineId.value && !weighedActive;
  if (numpadMode.value === "disc_brl" && fixedDiscountBlocked.value) return false;
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


function bump(lineId: string, emitName: "increment" | "decrement") {
  if (props.loading || props.saving) return;
  const line = props.items.find((entry) => entry.line_id === lineId);
  if (line && isWeighedLine(line)) return;
  selectedLineId.value = lineId;
  if (emitName === "increment" && line?.fired) {
    addLike(lineId, 1);
    return;
  }
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
  // Com marcas, DÍGITO NÃO FAZ NADA (a quantidade é de uma linha): só o desconto aberto
  // nas marcadas recebe número.
  const typing = !selectMode.value || discountOpen.value;
  if (event.key >= "0" && event.key <= "9") {
    if (!typing) return;
    event.preventDefault();
    revealForKeyboard();
    onDigit(event.key);
  } else if (event.key === "Backspace") {
    if (!typing) return;
    event.preventDefault();
    revealForKeyboard();
    onBackspace();
  } else if (selectMode.value && event.key === "Escape") {
    // Esc desmarca tudo.
    event.preventDefault();
    unmarkAll();
  } else if (editorVisible.value && event.key === "Escape") {
    // v4: "Fechar · Esc". Fora de campo, o Esc da venda não tinha outro dono.
    event.preventDefault();
    closeEditor();
  } else if (event.key === "Delete") {
    // "Del remove" o objeto em foco (sempre com a confirmação e o Desfazer).
    event.preventDefault();
    if (selectMode.value) batchRemove();
    else askRemove(activeLineId.value);
  } else if (editorVisible.value && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
    // v4: "↑↓ troca a linha" com o editor aberto.
    event.preventDefault();
    const index = props.items.findIndex((entry) => entry.line_id === activeLineId.value);
    const next = props.items[Math.max(0, Math.min(props.items.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)))];
    if (next) selectLine(next.line_id);
  }
}
/** O teclado físico digitou: o editor volta à vista. */
function revealForKeyboard() {
  if (!selectMode.value) editorClosed.value = false;
}
onMounted(() => window.addEventListener("keydown", onWindowKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onWindowKeydown));
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
async function focusItem(lineId = activeLineId.value) {
  const buttons = Array.from(
    receiptList.value?.querySelectorAll<HTMLButtonElement>(
      "[data-item-select]",
    ) || [],
  );
  const button =
    buttons.find((el) => el.dataset.itemSelect === lineId) || buttons[0];
  if (!button) return;
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
    toggleSelect(id);
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
    else if (selectMode.value) unmarkAll();
    else closeEditor();
  }
}
// O envio automático espera o rascunho e as marcas (o relógio mora na página).
const autoFireHeld = computed(() => Boolean(noteDraft.value) || discountOpen.value || selectMode.value);
watch(autoFireHeld, (held) => emit("autoFireHold", held), { immediate: true });

// F9 e F10 com marcas agem SÓ nelas (decisão 4 do dono; a tecla anunciada no botão faz o
// que o botão faz). Devolvem false sem marcas, e a página faz o de sempre.
function fireSelection(): boolean {
  if (!selectMode.value) return false;
  batchFire();
  return true;
}
function moveSelection(): boolean {
  if (!canMove.value || !props.hasOpenTab || !selectMode.value) return false;
  if (!props.loading && !props.offline) emit("move", selection.value.lineIds, "transfer");
  return true;
}

defineExpose({ focusItem, onDigit, onBackspace, fireSelection, moveSelection });
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
        :color="!fireCell.disabled ? 'primary' : 'neutral'"
        variant="outline"
        :loading="firing"
        block
        class="h-full justify-center bg-default font-semibold"
        :disabled="fireCell.disabled || firing"
        :aria-busy="firing || undefined"
        :shortcut="coarsePointer || fireCell.disabled ? undefined : 'F9'"
        aria-keyshortcuts="F9"
        :title="fireCell.title"
        data-pos-fire
        :data-pos-fire-marked="fireCell.onlyMarked ? '' : undefined"
        @click="onFireCell"
      >
        <template v-if="fireCell.count" #trailing>
          <OperatorCountChip
            :count="fireCell.count"
            :aria-label="`${fireCell.count} ${fireCell.count === 1 ? 'item' : 'itens'} a enviar`"
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
          <div v-else-if="cell === 'remove' && (activeItem || selectMode)" class="op-fit-scope h-full w-full">
            <OperatorButton
              v-bind="REMOVE_FIT"
              :size="controlSize"
              color="error"
              variant="outline"
              block
              class="h-full justify-center bg-default font-semibold"
              :shortcut="coarsePointer ? undefined : 'Del'"
              aria-keyshortcuts="Delete"
              :title="selectMode ? 'Remover as marcadas (Del), com confirmação e desfazer' : 'Remover (Del), com confirmação e desfazer'"
              :disabled="mutationBusy"
              data-pos-line-remove
              @click="selectMode ? batchRemove() : activeItem && askRemove(activeItem.line_id)"
            />
          </div>
          <div v-else-if="cell === 'move'" class="op-fit-scope h-full w-full">
            <OperatorButton
              label="Transferir"
              icon="i-lucide-arrow-right-left"
              :size="controlSize"
              color="neutral"
              variant="outline"
              block
              class="h-full justify-center"
              :shortcut="coarsePointer ? undefined : 'F10'"
              aria-keyshortcuts="F10"
              :disabled="loading || offline"
              :title="offline ? 'Transferir volta com a conexão' : 'Transferir as marcadas para outra comanda (F10)'"
              data-pos-batch-move
              @click="$emit('move', selection.lineIds, 'transfer')"
            />
          </div>
          <ReuseFireButton v-else-if="cell === 'fire'" />
          <OperatorButton
            v-else-if="cell === 'discount' && (activeItem || selectMode)"
            :label="selectMode ? 'Desconto' : discountButtonLabel"
            :short-label="(!selectMode && discountShortLabel) || undefined"
            icon="i-lucide-percent"
            :size="controlSize"
            color="neutral"
            variant="outline"
            active-color="primary"
            active-variant="solid"
            :active="discountOpen"
            block
            class="h-full justify-center"
            :class="!selectMode && !discountOpen && activeItem?.discount?.value ? 'font-semibold' : ''"
            :aria-pressed="discountOpen"
            :disabled="mutationBusy || offline"
            :title="offline ? 'Desconto volta com a conexão' : undefined"
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
            v-else-if="cell === 'note' && (activeItem || selectMode)"
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
      <!-- Z1 · O CABEÇALHO DA COMANDA (h-16, a altura da barra do topo da venda; as duas
           divisórias correm na mesma linha). Nunca troca de conteúdo: o que a comanda É
           (itens, linhas, a cozinha em palavra com o QUANDO do envio automático) e a
           porta do que age na comanda inteira sem marcar nada (Comanda ⋯). -->
      <header
        class="shrink-0 border-b border-border"
        :class="sheet ? '' : 'h-16'"
        data-pos-ticket-header
      >
        <div class="flex h-full flex-col justify-center gap-0.5 pr-2 pl-3.5" :class="sheet ? 'min-h-14 py-1.5' : ''">
          <div class="flex items-center gap-2">
            <div class="min-w-0 flex-1">
              <h3 v-if="sheet" class="op-title tnum [overflow-wrap:anywhere]" data-pos-sheet-title>{{ tabTitle ? `${tabTitle} · ` : "" }}{{ cartUnits }} {{ cartUnits === 1 ? "item" : "itens" }}</h3>
              <div v-else class="flex items-baseline gap-x-1.5 whitespace-nowrap">
                <h3 class="op-title tnum" data-pos-ticket-count>{{ cartUnits }} {{ cartUnits === 1 ? "item" : "itens" }}</h3>
                <span v-if="items.length" class="hidden op-micro text-muted-foreground tnum @min-[23rem]:inline">em {{ items.length }} {{ items.length === 1 ? "linha" : "linhas" }}</span>
              </div>
            </div>
            <OperatorMoreMenu
              v-if="showTabMenu"
              :items="tabMenuItems"
              label="Ações da comanda: transferir itens, juntar, liberar"
              :size="controlSize"
              class="shrink-0"
              data-pos-tab-menu
            />
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
          <!-- O estado da cozinha, numa linha discreta: o que falta, o que já foi e QUANDO o
               envio automático manda (o ajuste mora em Ajustes › Envio à cozinha; o toque
               leva lá). Sem conexão, o motivo no lugar do automático. -->
          <p v-if="fireBar.visible" class="flex items-center gap-x-1.5 op-micro whitespace-nowrap text-muted-foreground" data-pos-kitchen-state>
            <Icon :name="offline ? 'lucide:wifi-off' : 'lucide:chef-hat'" class="size-3.5 shrink-0" aria-hidden="true" />
            <span v-if="kitchenStateText">{{ kitchenStateText }}</span>
            <template v-if="!sheet || offline">
              <span v-if="kitchenStateText" aria-hidden="true">·</span>
              <span v-if="!kitchenState.linksToSettings" class="font-medium text-warning" data-pos-kitchen-offline><span :class="kitchenState.auto.wide ? 'hidden @min-[30rem]:inline' : 'hidden @min-[24rem]:inline'">{{ kitchenState.auto.full }}</span><span :class="kitchenState.auto.wide ? '@min-[30rem]:hidden' : '@min-[24rem]:hidden'">{{ kitchenState.auto.short }}</span></span>
              <NuxtButton
                v-else
                color="neutral"
                variant="ghost"
                class="h-auto min-h-0 rounded-sm p-0 op-micro font-normal text-muted-foreground underline-offset-2 hover:bg-transparent hover:text-foreground hover:underline"
                :title="autoFire ? 'Envio automático ligado na estação destes itens: vão ao sair da comanda ou depois de 90 s sem mudança (Ajustes › Envio à cozinha)' : 'Envio automático desligado (Ajustes › Envio à cozinha)'"
                :aria-label="kitchenState.auto.full"
                data-pos-auto-fire
                :data-auto-fire="autoFire ? 'on' : 'off'"
                @click="$emit('autoFireSettings')"
              ><span :class="kitchenState.auto.wide ? 'hidden @min-[30rem]:inline' : 'hidden @min-[24rem]:inline'">{{ kitchenState.auto.full }}</span><span :class="kitchenState.auto.wide ? '@min-[30rem]:hidden' : '@min-[24rem]:hidden'">{{ kitchenState.auto.short }}</span></NuxtButton>
            </template>
          </p>
        </div>
      </header>

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
          <!-- A CAIXA DE MARCAR mora na margem esquerda da linha (w-7, o lugar que antes era
               o recuo de 14 px), em posição ABSOLUTA: aparecer ou sumir nunca empurra a
               quantidade, o nome ou o preço. No mouse ela aparece no hover e no foco da
               linha; com marcadas, fica em todas. No toque, com a linha aberta (sem hover)
               ou pelo toque longo. -->
          <li
            v-for="item in items"
            :key="item.line_id"
            class="group/line relative flex flex-wrap items-stretch border-b border-border"
            :aria-current="activeLineId === item.line_id ? 'true' : undefined"
            :class="
              isSelected(item.line_id)
                ? 'bg-primary/10'
                : activeLineId === item.line_id && editorVisible
                  ? 'bg-primary/10 shadow-[inset_4px_0_0_var(--primary)]'
                  : 'hover:bg-muted/50'
            "
            :data-pos-line-marked="isSelected(item.line_id) ? '' : undefined"
          >
            <span
              class="absolute inset-y-0 left-0 z-10 flex w-7 items-center justify-center transition-opacity motion-reduce:transition-none"
              :class="selectMode || isSelected(item.line_id) || (coarsePointer && editorVisible) ? 'opacity-100' : 'opacity-0 group-hover/line:opacity-100 group-focus-within/line:opacity-100'"
              :data-pos-line-mark="item.line_id"
              @click.stop.prevent="toggleSelect(item.line_id, $event.shiftKey)"
            >
              <NuxtCheckbox
                :model-value="isSelected(item.line_id)"
                :aria-label="`Marcar ${item.name}`"
                tabindex="-1"
              />
            </span>
            <NuxtButton
              color="neutral"
              variant="ghost"
              class="grid min-h-12 min-w-0 flex-1 grid-cols-[2.25rem_minmax(0,1fr)_auto] items-center gap-x-2.5 rounded-none py-1.5 pr-3.5 pl-7 text-left font-normal hover:bg-transparent focus-visible:outline-none"
              :data-item-select="item.line_id"
              :aria-label="`Editar ${item.name}`"
              :aria-pressed="selectMode ? isSelected(item.line_id) : activeLineId === item.line_id"
              :aria-expanded="expandedLineId === item.line_id"
              :aria-controls="detailsId(item.line_id)"
              @focus="onRowFocus(item.line_id)"
              @click="onRowClick(item.line_id, $event)"
              @pointerdown="startPress(item.line_id, $event)"
              @pointerup="endPress"
              @pointerleave="endPress"
              @pointercancel="endPress"
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
                    :title="autoFireSkuSet.has(item.sku) ? `Vai sozinho para ${kitchenStations?.[item.sku]} ao sair da comanda ou depois de 90 s sem mudança` : `Vai para ${kitchenStations?.[item.sku]} quando for enviada`"
                    data-pos-line-goes-to-kitchen
                    ><Icon name="lucide:chef-hat" class="size-3.5" aria-hidden="true" />{{ autoFireSkuSet.has(item.sku) && !offline ? "vai sozinho" : "vai à cozinha" }}</span
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
              >
            </div>
          </li>
        </ul>
      </div>

      <!-- Z3 · O BLOCO DE AÇÃO: colado no pé da lista, borda primária em cima, só quando
           há foco. Diz no título o OBJETO (a linha aberta, ou "3 linhas marcadas · 5
           itens · R$ 61,70") e os verbos ficam nas MESMAS posições para 1 ou para N:
           Remover no alto à direita, Desconto e Observação embaixo; só o canto da
           Quantidade (que é de uma linha) vira Transferir. O raro mora no ⋯. Desconto e
           observação abrem AQUI, no lugar da grade, com Cancelar e Aplicar. -->
      <section
        v-if="blockVisible"
        class="shrink-0 border-t-2 border-primary bg-card px-3 pt-2 pb-2 shadow-[0_-10px_24px_rgb(0_0_0/.10)]"
        :aria-label="selectMode ? 'Linhas marcadas' : 'Linha aberta'"
        data-pos-line-editor
        :data-pos-block="selectMode ? 'marked' : 'line'"
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
            <OperatorMoreMenu v-if="lineMenuItems.length" :items="lineMenuItems" label="Mais ações da linha" size="xl" data-pos-line-menu />
          </div>
        </template>
        <!-- O CABEÇALHO do bloco: o que se edita (ou o que está marcado) e a dica do
             teclado do MOMENTO. A divisória separa a leitura dos controles. -->
        <template v-if="!selectMode && (lineControlsInGrid || lineEditing === 'note') && activeItem">
          <div class="flex items-start gap-2">
            <!-- Três peças que quebram como blocos (o nome inteiro, nunca cortado): na
                 coluna estreita o preço desce de linha em vez de se sobrepor. -->
            <p class="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-1 pt-1 op-label" data-pos-line-editor-title>
              <span class="text-muted-foreground">{{ lineEditing === "discount" ? "Desconto em" : lineEditing === "note" ? "Observação em" : "Editando" }}</span>
              <b class="min-w-0 font-semibold text-foreground [overflow-wrap:anywhere]">{{ activeItem.name }}</b>
              <span class="whitespace-nowrap text-muted-foreground tnum">· {{ formatBRL(unitChargedQ(activeItem)) }}{{ isWeighedLine(activeItem) ? "/kg" : " cada" }}</span>
            </p>
            <OperatorMoreMenu
              v-if="lineMenuItems.length && !lineEditing"
              :items="lineMenuItems"
              label="Mais ações da linha"
              class="-mt-0.5 shrink-0"
              data-pos-line-menu
            />
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
        <template v-else-if="selectMode">
          <div class="flex items-start gap-2">
            <p class="min-w-0 flex-1 pt-1 op-label font-semibold tnum [overflow-wrap:anywhere]" data-pos-marked-title>
              <template v-if="lineEditing === 'discount'"><span class="font-normal text-muted-foreground">Desconto em </span></template>
              <template v-else-if="lineEditing === 'note'"><span class="font-normal text-muted-foreground">Observação em </span></template>{{ marked.title }}
            </p>
            <OperatorMoreMenu v-if="batchMenuItems.length && !lineEditing" :items="batchMenuItems" label="Mais ações nas marcadas" class="-mt-0.5 shrink-0" data-pos-marked-menu />
            <NuxtButton
              color="neutral"
              variant="ghost"
              icon="i-lucide-x"
              square
              class="-mt-0.5 -mr-1 shrink-0"
              aria-label="Desmarcar tudo"
              aria-keyshortcuts="Escape"
              title="Desmarcar tudo (Esc)"
              data-pos-unmark
              @click="unmarkAll"
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
          <p class="col-span-2 -mt-1 op-micro text-muted-foreground" data-pos-note-help>{{ offline ? "A observação vai quando a conexão voltar." : noteDraft.lineIds.length > 1 ? `Vale para as ${noteDraft.lineIds.length} linhas marcadas e sai com elas para a cozinha.` : "A observação sai junto com o item para a cozinha." }}</p>
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
            :disabled="mutationBusy || (mode.ref === 'disc_brl' && fixedDiscountBlocked)"
            :title="mode.ref === 'disc_brl' && fixedDiscountBlocked ? 'Peça pesada: desconto só em %' : undefined"
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
          <template v-if="!touchEditor">
            <NuxtButton :size="controlSize" color="neutral" variant="outline" block class="justify-center" label="Cancelar" data-pos-edit-cancel @click="cancelDiscount" />
            <NuxtButton :size="controlSize" color="primary" block class="justify-center" label="Aplicar" :disabled="mutationBusy || !discountTargets.length" data-pos-edit-apply @click="applyDiscount" />
          </template>
        </div>

        <!-- A GRADE: da linha aberta (quantidade | Remover; Desconto | Observação) ou das
             marcadas (Transferir | Remover; Desconto | Observação), nas mesmas posições. -->
        <ReuseControlGrid v-else-if="selectMode" :rows="batchRows" block="marked" />
        <ReuseControlGrid v-else-if="lineControlsInGrid && activeItem" :rows="lineRows" block="line" />

        <!-- A LINHA JÁ NA COZINHA ganhou observação: a cozinha recebeu sem ela. O aviso
             oferece a ação (cancelar e enviar de novo, o que o servidor já faz), na cor
             do aviso, e se dispensa. -->
        <NuxtAlert
          v-if="resendOffer && !lineEditing && !selectMode"
          class="mt-2"
          color="info"
          variant="subtle"
          icon="i-lucide-chef-hat"
          title="A cozinha recebeu esta linha sem a observação."
          orientation="vertical"
          :actions="alertActions('info', [
            { label: 'Reenviar com a observação', disabled: offline || firing, onClick: resendWithNote },
            { label: 'Agora não', onClick: () => { resendOffer = ''; } },
          ])"
          data-pos-resend-offer
        />

        <!-- Sem conexão: o que precisa do servidor fica apagado, e a frase diz por quê. -->
        <p
          v-if="offline && !lineEditing && !lineAdjustmentsBlocked"
          class="mt-2 flex items-start gap-1.5 op-micro text-muted-foreground"
          data-pos-block-offline
        >
          <Icon name="lucide:wifi-off" class="mt-0.5 size-3.5 shrink-0" />
          <span>Sem conexão: desconto{{ selectMode ? " e transferir voltam" : " volta" }} com a conexão.</span>
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
              :disabled="mutationBusy || lineAdjustmentsBlocked || offline"
              :label="discountOpen ? 'Cancelar' : 'Desconto'"
              data-pos-line-discount
              @click="discountOpen ? cancelDiscount() : toggleDiscount()"
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
              icon="i-lucide-check"
              class="h-14 justify-center gap-1.5 px-1.5 text-sm font-semibold sm:h-16"
              :ui="SIDE_KEY_UI"
              :color="discountOpen ? 'primary' : 'neutral'"
              data-pos-line-editor-close
              @click="discountOpen ? applyDiscount() : closeEditor()"
            >{{ discountOpen ? "Aplicar" : "Pronto" }}</NuxtButton>
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


      <!-- Z4 · O PÉ, sempre o mesmo e com a mesma altura: Enviar | Dividir conta (o Enviar
           segue o foco: com marcadas, "Enviar 3 marcadas") e o Pagamento, que é SEMPRE a
           comanda inteira (dinheiro não muda de sentido por causa de uma marca). -->
      <!-- FOLHA ABERTA (v4 tablet b): pagar direto daqui, pelos meios eletrônicos que
           o dispositivo leva à mesa. "Outras formas" abre o Pagamento de sempre. -->
      <div v-if="sheet && quickPayments?.length && !primaryLabel" class="shrink-0 border-t border-border p-3" data-pos-sheet-pay>
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
        :class="blockVisible ? 'pt-0' : 'border-t border-border pt-3'"
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
