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
// - o teclado físico (as teclas da venda, pelo mapa canônico do kit), Enter recebe e
//   Esc volta ao detalhe;
// - a Tela do cliente acompanha o recebimento (o valor e para quem);
// - o PDV não trava por ociosidade com o cliente pagando (P2-14);
// - o corpo da rota (`handOverBody`): o dinheiro vira o que ele paga de fato, e
//   as cédulas vão inteiras como recebido;
// - o SALDO EM PIX (#2897): escolhido o Pix (sozinho, no valor inteiro), a página
//   pede a cobrança Pix do pedido e esta tela mostra o MESMO QR da venda
//   (`PosPaymentResult`), na Tela do cliente também, e espera pelo MESMO status
//   (`usePixStatusPoll`). Pago, a página entrega; não chegou, "Gerar outro Pix" ou
//   "Receber em outra forma" (que cancela este Pix antes, no servidor).
import { toast } from "vue-sonner";

import type { BalancePixStatus, HandOverBody } from "~/presentation/balanceCharge";
import { balanceCharge, handOverBody, handOverMethods, paysBalanceWithPix } from "~/presentation/balanceCharge";
import { paymentProofView } from "~/presentation/payment";
import { usePixStatusPoll } from "~/composables/usePixStatusPoll";
import { pendingPixDeadlineMs } from "~/utils/pendingPixStore";
import { handOverCustomerDisplaySnapshot } from "~/presentation/customerDisplay";
import { BALANCE_PAYMENT_SHORTCUTS, type BalancePaymentContext } from "~/presentation/paymentKeys";
import { customerLine } from "~/presentation/preorders";
import { useCustomerDisplayPublisher } from "~/composables/useCustomerDisplay";
import { usePosTenders } from "~/composables/usePosTenders";
import { useOperatorShortcutMap } from "../../../operator-kit/app/composables/useOperatorShortcutMap";
import type { POSPaymentResultProjection, POSPaymentTenderDraft, POSProjection } from "~/types/pos";
import type { PreorderDetail } from "~/types/preorders";

const props = defineProps<{
  detail: PreorderDetail;
  pos: POSProjection | null;
  busy?: boolean;
  /** Quem continua operando (o diálogo do gerente da tela, se um dia aparecer). */
  operatorName?: string;
  /** O Pix do saldo cobrado no balcão (o QR, no formato da venda); `null` antes dele. */
  pixProof?: POSPaymentResultProjection | null;
}>();

const emit = defineEmits<{
  back: [];
  /** O corpo da rota e o troco que a tela mostrou (para o aviso de pronto). */
  submit: [body: HandOverBody, changeQ: number];
  /** O saldo vai em Pix: a página pede a cobrança (ou outra, depois da que venceu). */
  pix: [];
  /** O Pix entrou: a página entrega. O valor é o que o Pix cobrou. */
  pixPaid: [amountQ: number];
  /** O operador desistiu do Pix na tela: volta às formas (receber cancela o Pix antes). */
  pixLeave: [];
  /** Onde a espera está (a página põe o aviso que resolve no topo). */
  pixStatus: [status: BalancePixStatus];
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
  // Pix sozinho, no valor inteiro (a tela já travou o resto): a cobrança Pix do
  // pedido, do jeito da venda que fecha em Pix.
  if (paysBalanceWithPix(lines.value, charge.value.amountQ)) {
    emit("pix");
    return;
  }
  emit("submit", handOverBody(lines.value, charge.value.amountQ), paymentChangeQ.value);
}

// ── O saldo em Pix: o QR da venda e a espera da venda ──
const pixView = computed(() => paymentProofView(props.pixProof ?? null));
const pixStatus = ref<BalancePixStatus>("idle");
watch(pixStatus, (status) => emit("pixStatus", status));
const pixPoll = usePixStatusPoll();
watch(() => props.pixProof?.intent_ref || "", (intentRef) => {
  pixPoll.stop();
  if (!intentRef || !props.pixProof) {
    pixStatus.value = "idle";
    return;
  }
  const amountQ = props.pixProof.amount_q;
  pixStatus.value = "polling";
  pixPoll.start(props.detail.ref, {
    deadlineMs: pendingPixDeadlineMs({ since: new Date().toISOString(), expiresAt: props.pixProof.expires_at }),
    onOutcome: (outcome) => {
      if (outcome === "paid") {
        pixStatus.value = "paid";
        emit("pixPaid", amountQ);
        return;
      }
      pixStatus.value = "expired";
    },
  });
}, { immediate: true });
onBeforeUnmount(() => pixPoll.stop());

/** Desistir do Pix na tela: as formas voltam limpas (o servidor cancela o Pix ao receber). */
function leavePix() {
  pixPoll.stop();
  lines.value = [];
  tenders.clearSelection();
  tenders.resetSplit();
  emit("pixLeave");
}

// ── O que esta tela publica e segura ──
// A Tela do cliente acompanha o recebimento: o valor e para quem. Ao sair (voltar
// ou entregar), o publicador devolve a parede às boas-vindas.
const displaySnapshot = computed(() => handOverCustomerDisplaySnapshot({
  shopName: props.pos?.shop_name || "",
  amountDisplay: pixView.value?.amountDisplay || charge.value.amountDisplay,
  customerName: charge.value.customerName,
  orderRef: charge.value.orderRef,
  pix: pixView.value?.isPix ? { qrCodeSrc: pixView.value.qrCodeSrc, status: pixStatus.value } : null,
}));
useCustomerDisplayPublisher(displaySnapshot);

// P2-14: com o Pagamento aberto o PDV não trava por ociosidade, como na venda.
const paymentHold = useState("pos-payment-hold", () => false);
onMounted(() => { paymentHold.value = true; });

// O PRÓXIMO FOCO ao abrir: escolher a forma. O foco de teclado vai para a primeira
// (Enter lança ela; com o saldo coberto, Enter recebe e entrega), sem reorganizar a
// tela em torno dela: o valor a receber continua à vista.
const root = useTemplateRef<HTMLElement>("root");
const { reveal } = useNextFocus();
onMounted(() => {
  reveal(() => root.value?.querySelector<HTMLElement>("[data-payment-method]:not(:disabled)") ?? null, { align: "center" });
});
onBeforeUnmount(() => { paymentHold.value = false; });

// ── O teclado físico: as teclas da tela de Pagamento, pelo mapa canônico do kit ──
const workspace = ref<{
  validate: () => void;
  pressMethodKey: (letter: string) => boolean;
  pressExact: () => boolean;
  openSplit: () => void;
} | null>(null);

const shortcutContexts = computed(() => {
  const active = new Set<BalancePaymentContext>();
  // Com o QR na tela não há forma a editar: só o Esc (voltar) vale.
  if (props.pixProof) return active;
  if (selectedTenderIndex.value >= 0) active.add("tender-selected");
  // Enter recebe pelo MESMO caminho do toque (a maquininha e o troco alto conferem antes).
  if (paymentCovered.value && !props.busy) active.add("covered");
  return active;
});
const shortcutHandlers: Record<string, (event: KeyboardEvent) => void> = {
  "balance.comma": () => tenders.tenderComma(),
  "balance.backspace": () => tenders.tenderBackspace(),
  "balance.exact": () => { workspace.value?.pressExact(); },
  "balance.receive": () => workspace.value?.validate(),
  "balance.split": () => workspace.value?.openSplit(),
  "balance.back": () => emit("back"),
};
for (const command of BALANCE_PAYMENT_SHORTCUTS) {
  if (command.id.startsWith("balance.digit.")) {
    const digit = command.id.slice("balance.digit.".length);
    shortcutHandlers[command.id] = () => tenders.tenderDigit(digit);
  } else if (command.id.startsWith("balance.method.")) {
    const letter = command.id.slice("balance.method.".length);
    shortcutHandlers[command.id] = () => { workspace.value?.pressMethodKey(letter); };
  }
}
useOperatorShortcutMap(BALANCE_PAYMENT_SHORTCUTS, shortcutHandlers, shortcutContexts);

// O saldo mudou por fora (outro balcão recebeu, a encomenda foi editada): as
// linhas lançadas para o valor antigo não valem mais, e a conta recomeça.
watch(() => props.detail.counter.hand_over.amount_q, (amount, before) => {
  // Com o Pix na tela, o saldo mudar é o Pix entrando: quem fala é a espera dele.
  if (amount === before || props.pixProof) return;
  lines.value = [];
  tenders.clearSelection();
  tenders.resetSplit();
  toast.info("O saldo da encomenda mudou. Escolha a forma de novo.");
});
</script>

<template>
  <div ref="root" class="flex h-full min-h-0 flex-col" data-preorder-balance-payment>
    <!-- O SALDO EM PIX: o mesmo QR e a mesma espera da venda em Pix
         (`PosPaymentResult`). A saída fica sempre à vista: o cliente pode
         desistir do Pix e pagar de outra forma, e receber cancela este Pix antes. -->
    <section
      v-if="pixProof && pixView"
      class="mx-auto grid w-full max-w-md content-start gap-4 md:py-4"
      aria-label="Pix da encomenda"
      data-balance-pix
    >
      <header class="grid gap-1 text-center">
        <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Encomenda {{ charge.orderRef }}</p>
        <p class="text-lg font-semibold" data-balance-pix-customer>{{ charge.customerName }}</p>
      </header>
      <PosPaymentResult :proof="pixView" :status="pixStatus" large class="w-full text-left" />
      <div class="grid gap-2">
        <NuxtButton
          v-if="pixStatus === 'expired'"
          size="xl"
          block
          class="justify-center"
          icon="i-lucide-qr-code"
          label="Gerar outro Pix"
          :loading="busy"
          :disabled="busy"
          data-balance-pix-again
          @click="emit('pix')"
        />
        <NuxtButton
          size="xl"
          block
          color="neutral"
          variant="outline"
          class="justify-center"
          icon="i-lucide-banknote"
          label="Receber em outra forma"
          :disabled="busy || pixStatus === 'paid'"
          data-balance-pix-leave
          @click="leavePix"
        />
      </div>
    </section>
    <PosPaymentWorkspace
      v-else
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
