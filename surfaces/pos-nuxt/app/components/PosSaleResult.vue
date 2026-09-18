<script setup lang="ts">
// Tela de RESULTADO pós-venda (padrão Odoo/Shopify): tela cheia no fluxo de
// venda, no lugar do banner de antes. O troco é o herói (tipografia display),
// a prova digital (QR PIX / link do cartão) tem palco, e o CTA dominante é
// "Nova venda". Comportamento por método:
//   - dinheiro COM troco → a tela NUNCA some sozinha (confirmação explícita);
//   - pagamento exato/cartão/PIX confirmado → auto-avanço curto com contagem
//     visível e cancelável (qualquer toque cancela; reduced-motion desliga);
//   - PIX aguardando → sair exige toque explícito (o composable transforma a
//     prova pendente num chip no header, com o polling seguindo).
import {
  autoAdvanceSeconds,
  changeDisplay as toChangeDisplay,
  courierChangeLine,
  danfeOffer,
  enterAdvances,
  orderReadback,
  paymentFailed,
  pixAwaiting,
  type PixPollStatus,
  type PosSaleResultSnapshot,
  saleResultTitle,
} from "~/presentation/saleResult";

const props = defineProps<{
  result: PosSaleResultSnapshot;
  pixStatus: PixPollStatus;
  canCancel: boolean;
  /** A nota aberta na tela ("" = sem acesso; a bobina independe disto). */
  danfeScreenUrl: string;
  printingReceipt: boolean;
  printingDanfe: boolean;
  /** Reenvio do link de pagamento em voo (só o pedido de link usa). */
  resendingLink?: boolean;
  /** A ficha do pedido (encomenda) está saindo na bobina. */
  printingTicket?: boolean;
}>();

const emit = defineEmits<{
  newSale: [];
  printReceipt: [];
  printDanfe: [];
  /** ENCOMENDA: a ficha do pedido para o painel de parede. */
  printTicket: [];
  cancelSale: [];
  paymentNotice: ["send" | "resend"];
}>();

const readback = computed(() => orderReadback(props.result));
const title = computed(() => props.result.salesMode === "order"
  ? paymentFailed(props.result.payment) ? "Encomenda registrada, cobrança não criada" : "Encomenda registrada"
  : saleResultTitle(props.result.receipt.customerName, props.result.payment));
const chargeFailed = computed(() => paymentFailed(props.result.payment));
const changeDisplay = computed(() => toChangeDisplay(props.result.changeQ));
// COBRANÇA NA ENTREGA/RETIRADA: o troco ainda não saiu da gaveta — é o que o
// entregador vai separar. Linha discreta, sem herói e sem segurar a tela.
const courierChange = computed(() => courierChangeLine(props.result.courierChangeQ));
// A DANFE por EXISTÊNCIA da nota, não por previsão (ver `danfeOffer`).
const danfe = computed(() => danfeOffer(props.result.fiscalState));
const pixPending = computed(() => pixAwaiting(props.result.payment, props.pixStatus));
const enterHint = computed(() => enterAdvances({
  changeQ: props.result.changeQ,
  payment: props.result.payment,
  pixStatus: props.pixStatus,
  salesMode: props.result.salesMode,
}));

// Auto-avanço: decidido UMA vez, na entrada da tela (presentation pura decide;
// aqui só corre o relógio). Qualquer toque na tela cancela a contagem — mexer
// nos verbos secundários é "quero ficar"; o CTA avança de todo jeito.
const countdown = ref(0);
let countdownTimer: number | null = null;
function cancelCountdown() {
  if (countdownTimer) {
    window.clearInterval(countdownTimer);
    countdownTimer = null;
  }
  countdown.value = 0;
}
onMounted(() => {
  // A encomenda precisa ficar disponível para conferir e imprimir a ficha do pedido.
  if (props.result.salesMode === "order") return;
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
  const seconds = autoAdvanceSeconds({
    changeQ: props.result.changeQ,
    payment: props.result.payment,
    pixStatus: props.pixStatus,
    reducedMotion,
  });
  if (!seconds) return;
  countdown.value = seconds;
  countdownTimer = window.setInterval(() => {
    countdown.value -= 1;
    if (countdown.value <= 0) {
      cancelCountdown();
      emit("newSale");
    }
  }, 1000);
});
onBeforeUnmount(() => cancelCountdown());

function onNewSale() {
  cancelCountdown();
  emit("newSale");
}
</script>

<template>
  <section
    class="flex h-full min-h-0 flex-col items-center justify-center gap-6 overflow-y-auto px-4 py-6 text-center"
    data-sale-result
    @pointerdown.capture="cancelCountdown"
  >
    <!-- Confirmação + identidade do pedido. ⚠️ O selo verde é uma AFIRMAÇÃO
         sobre o dinheiro: só aparece quando houve cobrança. Com o gateway
         recusando, o mesmo check dizia "concluída" numa venda que ninguém
         cobrou. -->
    <div class="grid justify-items-center gap-2">
      <div
        class="grid size-12 place-items-center rounded-full border"
        :class="chargeFailed
          ? 'border-destructive/40 bg-destructive/10 text-destructive'
          : 'border-success/40 bg-success/10 text-success'"
      >
        <Icon :name="chargeFailed ? 'lucide:alert-triangle' : 'lucide:check'" class="size-6" />
      </div>
      <h2 class="text-3xl font-semibold tracking-tight">{{ title }}</h2>
      <p class="text-sm text-muted-foreground">
        Pedido <span class="font-mono">{{ result.orderRef }}</span>
        <template v-if="result.receipt.tabDisplay"> · Comanda {{ result.receipt.tabDisplay }}</template>
        · {{ result.receipt.totalDisplay }}
      </p>
    </div>

    <!-- LEITURA DE VOLTA da encomenda: como e quando, ditos em voz alta antes
         de desligar o telefone. É a última chance de pegar um "era sábado, não
         sexta" — depois disso o combinado só existe no Gestor. -->
    <div
      v-if="readback"
      class="grid w-full max-w-md gap-2 rounded-md border bg-card p-4 text-left"
      data-order-readback
      role="status"
    >
      <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Confirme com o cliente</p>
      <p v-if="readback.fulfillment" class="flex items-center gap-2 text-base font-semibold">
        <Icon :name="readback.fulfillment.startsWith('Entrega') ? 'lucide:bike' : 'lucide:store'" class="size-5 shrink-0 text-muted-foreground" />
        {{ readback.fulfillment }}
      </p>
      <p v-if="readback.schedule" class="flex items-center gap-2 text-base font-semibold">
        <Icon name="lucide:calendar-clock" class="size-5 shrink-0 text-muted-foreground" />
        {{ readback.schedule }}
      </p>
    </div>

    <!-- TROCO — o herói da tela quando existe. `aria-live` anuncia o valor. -->
    <div v-if="changeDisplay" class="grid justify-items-center gap-1" aria-live="polite" role="status">
      <p class="text-sm font-medium uppercase tracking-wide text-muted-foreground">Troco</p>
      <p class="text-7xl font-bold tabular-nums tracking-tight text-primary md:text-8xl">{{ changeDisplay }}</p>
      <p class="text-sm text-muted-foreground">Confira o troco antes de seguir para a próxima venda.</p>
    </div>
    <!-- TROCO A SEPARAR — cobrança na entrega/retirada: o dinheiro ainda não
         entrou, o troco é o que sai com o entregador. Nem herói, nem trava. -->
    <p v-else-if="courierChange" class="text-sm text-muted-foreground" data-courier-change>
      {{ courierChange }}
    </p>

    <!-- NFC-e FALHOU — a venda existe, a nota não. Dito aqui, e não num toast
         que some: o próximo passo mora nas Últimas vendas (reenfileirar). -->
    <div
      v-if="danfe?.kind === 'failed'"
      class="grid w-full max-w-md gap-1 rounded-md border border-destructive/40 bg-destructive/5 p-4 text-left"
      role="alert"
      data-fiscal-failed
    >
      <p class="text-sm font-semibold text-destructive">{{ danfe.label }}</p>
    </div>

    <!-- COBRANÇA NÃO CRIADA. O caminho que não tinha tela: o pedido está de pé
         e o dinheiro não foi cobrado. Ela diz o que aconteceu e o que fazer, e
         segura a tela (o auto-avanço e o Enter estão desligados aqui). -->
    <div
      v-if="chargeFailed"
      class="grid w-full max-w-md gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-4 text-left"
      role="alert"
    >
      <p class="text-sm font-semibold text-destructive">
        O pagamento não foi criado no gateway.
      </p>
      <p class="text-sm text-muted-foreground">
        {{ result.payment?.amountDisplay }} em
        {{ result.payment?.method === 'pix' ? 'Pix' : result.payment?.method === 'link' ? 'link de pagamento' : 'cartão' }}
        segue <strong class="text-foreground">em aberto</strong>. Receba de outra forma e acerte o
        pedido no gestor — não trate esta venda como paga.
      </p>
    </div>

    <!-- Prova digital: QR PIX grande + status vivo do polling, ou o link do
         checkout do cartão (mesmo componente do fluxo de pagamento). -->
    <PosPaymentResult
      v-if="result.payment?.hasProof"
      :proof="result.payment"
      :status="pixStatus"
      :resending="resendingLink"
      :delivery="result.paymentDelivery"
      large
      class="w-full max-w-md text-left"
      @payment-notice="emit('paymentNotice', $event)"
    />

    <!-- Hierarquia única de ações (mesma disciplina do checkout): UM CTA
         primário; secundárias como botões UNIFORMES do mesmo peso; terciárias
         discretas porém alinhadas no mesmo grupo — nada de botão e link soltos
         disputando a mesma linha. Os handlers são os de sempre (agente do balcão). -->
    <div class="grid justify-items-center gap-3">
      <!-- CTA dominante -->
      <UiButton size="lg" class="h-14 min-w-64 gap-2 text-base" @click="onNewSale">
        {{ pixPending ? "Nova venda mesmo assim" : "Nova venda" }}
        <OperatorKbd variant="inverse" aria-hidden="true">F2</OperatorKbd>
      </UiButton>
      <p v-if="countdown > 0" class="text-xs text-muted-foreground" role="status">
        Nova venda em {{ countdown }}s · toque em qualquer lugar para ficar
      </p>
      <p v-else-if="pixPending" class="text-xs text-muted-foreground">
        O PIX segue aguardando: ao sair, ele vira um aviso no topo até confirmar.
      </p>
      <p v-else-if="enterHint" class="text-xs text-muted-foreground">Enter também avança.</p>

      <!-- Secundárias: mesmo peso, mesmo tamanho -->
      <div class="flex flex-wrap items-center justify-center gap-2">
        <UiButton variant="outline" size="sm" class="gap-1.5" :disabled="printingReceipt" @click="emit('printReceipt')">
          <Icon name="lucide:printer" class="size-4" />
          Imprimir recibo
        </UiButton>
        <!-- A DANFE só é botão vivo quando a nota EXISTE. Na fila, o botão
             fica desabilitado e a impressão automática o promove quando o 409
             da bobina vira 200; aguardando pagamento, a frase diz o quando. -->
        <UiButton
          v-if="danfe?.kind === 'print' || danfe?.kind === 'queued'"
          variant="outline" size="sm" class="gap-1.5"
          :disabled="printingDanfe || danfe.kind === 'queued'"
          :aria-busy="danfe.kind === 'queued' ? 'true' : undefined"
          data-danfe-action
          @click="emit('printDanfe')"
        >
          <Icon :name="danfe.kind === 'queued' ? 'lucide:loader-circle' : 'lucide:printer'" class="size-4" :class="danfe.kind === 'queued' ? 'animate-spin' : ''" />
          {{ danfe.label }}
        </UiButton>
        <p
          v-else-if="danfe?.kind === 'awaiting_payment'"
          class="inline-flex h-8 items-center gap-1.5 px-2 text-xs text-muted-foreground"
          data-danfe-awaiting
        >
          <Icon name="lucide:clock" class="size-4" />
          {{ danfe.label }}
        </p>
        <!-- A FICHA DO PEDIDO mora AQUI, com as outras saídas de papel. Era um
             cartaz separado acima da tela, como se fosse outra coisa. -->
        <UiButton
          v-if="result.salesMode === 'order'"
          variant="outline" size="sm" class="gap-1.5"
          :disabled="printingTicket"
          @click="emit('printTicket')"
        >
          <Icon name="lucide:printer" class="size-4" />
          {{ printingTicket ? "Imprimindo…" : "Imprimir ficha do pedido" }}
        </UiButton>
        <UiButton v-if="result.salesMode === 'order'" variant="outline" size="sm" class="gap-1.5" :href="result.nextUrl">
          <Icon name="lucide:external-link" class="size-4" />
          Abrir no gestor
        </UiButton>
      </div>

      <!-- Terciárias: discretas, alinhadas num único grupo -->
      <div class="flex flex-wrap items-center justify-center gap-2">
        <UiButton
          v-if="danfe?.kind === 'print' && danfeScreenUrl"
          variant="ghost"
          size="sm"
          class="gap-1.5 text-muted-foreground hover:text-foreground"
          :href="danfeScreenUrl"
          target="_blank" rel="noopener"
        >
          <Icon name="lucide:eye" class="size-4" />
          Ver a nota
        </UiButton>
        <!-- Cancelar é EXCEÇÃO, não fluxo: entrada discreta que abre a
             confirmação destrutiva com desafio de PIN gerencial. -->
        <UiButton
          v-if="canCancel"
          variant="ghost"
          size="sm"
          class="gap-1.5 text-muted-foreground hover:text-destructive"
          @click="emit('cancelSale')"
        >
          <Icon name="lucide:undo-2" class="size-4" />
          Cancelar venda
        </UiButton>
      </div>
    </div>
  </section>
</template>
