<script setup lang="ts">
// RECEBER O SALDO da encomenda na tela de Pagamento (EXCELENCIA-PDV, WP-E5).
//
// Gesto de dinheiro tem UMA tela (dono, 16/11/2026: "precisamos dessa janela para
// dizer forma de pagamento/troco etc??? Já não temos mecanismo pra isso???"). O
// "Receber e entregar" do detalhe abre o MESMO `PosPaymentWorkspace` da venda, em
// modo saldo: o total é o que o servidor diz que falta receber; as formas são as
// que a entrega no balcão aceita (`handOverMethods`); as linhas, o teclado, as
// cédulas, o Exato, a divisão, a maquininha e a conferência do troco alto são os
// da venda (`usePosTenders`, o mesmo estado por trás da mesma tela).
//
// O que é DESTA tela, e só dela:
// - o teclado físico (a mesma régua da venda, `paymentKeyIntent`), Enter recebe e
//   Esc volta ao detalhe;
// - a Tela do cliente acompanha o recebimento (o valor e para quem);
// - o PDV não trava por ociosidade com o cliente pagando (P2-14);
// - o corpo da rota (`handOverBody`): o dinheiro vira o que ele paga de fato, e
//   as cédulas vão inteiras como recebido. A rota não muda (fronteira).
import { toast } from "vue-sonner";

import type { HandOverBody } from "~/presentation/balanceCharge";
import { balanceCharge, handOverBody, handOverMethods } from "~/presentation/balanceCharge";
import { handOverCustomerDisplaySnapshot } from "~/presentation/customerDisplay";
import { paymentKeyIntent } from "~/presentation/paymentKeys";
import { customerLine } from "~/presentation/preorders";
import { useCustomerDisplayPublisher } from "~/composables/useCustomerDisplay";
import { usePosTenders } from "~/composables/usePosTenders";
import { globalKeysBlocked } from "~/utils/keyboardGuard";
import type { POSPaymentTenderDraft, POSProjection } from "~/types/pos";
import type { PreorderDetail } from "~/types/preorders";

const props = defineProps<{
  detail: PreorderDetail;
  pos: POSProjection | null;
  busy?: boolean;
  /** Quem continua operando (o diálogo do gerente da tela, se um dia aparecer). */
  operatorName?: string;
}>();

const emit = defineEmits<{
  back: [];
  /** O corpo da rota e o troco que a tela mostrou (para o aviso de pronto). */
  submit: [body: HandOverBody, changeQ: number];
}>();

const charge = computed(() => balanceCharge({
  orderRef: props.detail.ref,
  customerName: customerLine(props.detail.counter.card),
  handOver: props.detail.counter.hand_over,
  card: props.detail.counter.card,
  items: props.detail.items ?? [],
  discountLines: props.detail.discount_lines ?? [],
}));

// As linhas desta cobrança. Nascem vazias: como na venda, nenhuma forma vem
// escolhida, e Receber só acende quando uma forma cobre o saldo.
const lines = ref<POSPaymentTenderDraft[]>([]);
const tenders = usePosTenders({
  tenders: () => lines.value,
  totalQ: () => charge.value.amountQ,
  // O saldo já é o número do servidor: não há review a esperar.
  totalStatus: () => "confirmed",
  totalPendingMessage: () => "",
  collection: () => "terminal",
});
const {
  paymentTotalQ,
  paymentRemainingQ,
  paymentChangeQ,
  paymentCovered,
  selectedTenderIndex,
  selectedTenderMethod,
  splitCount,
  splitPaidCount,
  splitNote,
} = tenders;

const methods = computed(() => handOverMethods(props.pos?.payment_methods ?? []));

function submit() {
  if (props.busy) return;
  emit("submit", handOverBody(lines.value, charge.value.amountQ), paymentChangeQ.value);
}

// ── O que esta tela publica e segura ──
// A Tela do cliente acompanha o recebimento: o valor e para quem. Ao sair (voltar
// ou entregar), o publicador devolve a parede às boas-vindas.
const displaySnapshot = computed(() => handOverCustomerDisplaySnapshot({
  shopName: props.pos?.shop_name || "",
  amountDisplay: charge.value.amountDisplay,
  customerName: charge.value.customerName,
  orderRef: charge.value.orderRef,
}));
useCustomerDisplayPublisher(displaySnapshot);

// P2-14: com o pagamento aberto o PDV não trava por ociosidade, como na venda.
const paymentHold = useState("pos-payment-hold", () => false);
onMounted(() => { paymentHold.value = true; });
onBeforeUnmount(() => { paymentHold.value = false; });

// ── O teclado físico: a mesma régua da venda ──
const workspace = ref<{
  validate: () => void;
  pressMethodKey: (letter: string) => boolean;
  pressExact: () => boolean;
} | null>(null);

function onKeydown(event: KeyboardEvent) {
  if (event.defaultPrevented || globalKeysBlocked()) return;
  const target = event.target as HTMLElement | null;
  const isEditing = !!target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
  if (isEditing) return;
  const intent = paymentKeyIntent(event, selectedTenderIndex.value >= 0);
  if (intent?.kind === "digit") { event.preventDefault(); tenders.tenderDigit(intent.digit); return; }
  if (intent?.kind === "comma") { event.preventDefault(); tenders.tenderComma(); return; }
  if (intent?.kind === "backspace") { event.preventDefault(); tenders.tenderBackspace(); return; }
  if (intent?.kind === "exact") { event.preventDefault(); workspace.value?.pressExact(); return; }
  if (intent?.kind === "letter") {
    if (workspace.value?.pressMethodKey(intent.letter)) event.preventDefault();
    return;
  }
  if (event.key === "Enter" && paymentCovered.value && !props.busy) {
    // Pelo MESMO caminho do toque: a maquininha e o troco alto conferem antes.
    event.preventDefault();
    workspace.value?.validate();
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    emit("back");
  }
}
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

// O saldo mudou por fora (outro balcão recebeu, a encomenda foi editada): as
// linhas lançadas para o valor antigo não valem mais, e a conta recomeça.
watch(() => props.detail.counter.hand_over.amount_q, (amount, before) => {
  if (amount === before) return;
  lines.value = [];
  tenders.clearSelection();
  tenders.resetSplit();
  toast.info("O saldo da encomenda mudou. Escolha a forma de novo.");
});
</script>

<template>
  <div class="flex h-full min-h-0 flex-col" data-preorder-balance-payment>
    <PosPaymentWorkspace
      ref="workspace"
      :balance="charge"
      sales-mode="counter"
      tab-display=""
      :items="[]"
      :has-open-tab="false"
      :fulfillment-options="[]"
      :payment-methods="methods"
      :payment-constraints="{}"
      :payment-collections="[]"
      :checkout-contract="pos?.checkout || null"
      :address-autocomplete="null"
      :customer-lookup="null"
      :search-results="[]"
      :search-busy="false"
      :review="null"
      :discount-types="[]"
      :discount-reasons="[]"
      discount-type="percent"
      discount-value=""
      discount-reason=""
      :manager-approved="false"
      manager-approval-error=""
      :managers="[]"
      :operator-name="operatorName || ''"
      fulfillment-type="pickup"
      :fulfillment-confirmed="true"
      payment-collection="terminal"
      :payment-tenders="lines"
      :split-count="splitCount"
      :split-paid-count="splitPaidCount"
      :split-note="splitNote"
      :selected-tender-index="selectedTenderIndex"
      :selected-tender-method="selectedTenderMethod"
      :payment-total-q="paymentTotalQ"
      :payment-remaining-q="paymentRemainingQ"
      :payment-change-q="paymentChangeQ"
      :payment-covered="paymentCovered"
      customer-name=""
      customer-phone=""
      customer-tax-id=""
      invoice-tax-id=""
      :wants-cpf-on-invoice="false"
      customer-email=""
      delivery-address=""
      :delivery-address-structured="{}"
      delivery-street-number=""
      delivery-neighborhood=""
      delivery-complement=""
      delivery-instructions=""
      delivery-date=""
      delivery-time-slot=""
      delivery-fee-override-input=""
      :delivery-fee-override="false"
      :delivery-fee-q="0"
      delivery-fee-source=""
      :delivery-distance-km="null"
      :delivery-slots="[]"
      :delivery-slots-pending="false"
      delivery-date-effective=""
      schedule-today=""
      :schedule-available-dates="[]"
      schedule-bottleneck-name=""
      schedule-ready-at=""
      :schedule-failed="false"
      schedule-max-date=""
      change-for-input=""
      order-notes=""
      :receipt-channels="[]"
      receipt-email=""
      :save-receipt-contact="null"
      :save-receipt-tax-id="null"
      :loading="!!busy"
      :lookup-busy="false"
      @back="emit('back')"
      @submit="submit"
      @add-tender="tenders.addTender"
      @remove-tender="tenders.removeTender"
      @select-tender="tenders.selectTender"
      @set-split-count="tenders.setSplitCount"
      @tender-digit="tenders.tenderDigit"
      @tender-comma="tenders.tenderComma"
      @tender-backspace="tenders.tenderBackspace"
      @tender-clear="tenders.tenderClear"
      @tender-add="tenders.tenderAdd"
      @tender-exact="tenders.tenderExact"
    />
  </div>
</template>
