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
  enterAdvances,
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
}>();

const emit = defineEmits<{
  newSale: [];
  printReceipt: [];
  printDanfe: [];
  cancelSale: [];
  resendLink: [];
}>();

const title = computed(() => saleResultTitle(props.result.receipt.customerName));
const changeDisplay = computed(() => toChangeDisplay(props.result.changeQ));
const pixPending = computed(() => pixAwaiting(props.result.payment, props.pixStatus));
const enterHint = computed(() => enterAdvances({
  changeQ: props.result.changeQ,
  payment: props.result.payment,
  pixStatus: props.pixStatus,
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
    <!-- Confirmação + identidade do pedido -->
    <div class="grid justify-items-center gap-2">
      <div class="grid size-12 place-items-center rounded-full border border-success/40 bg-success/10 text-success">
        <Icon name="lucide:check" class="size-6" />
      </div>
      <h2 class="text-3xl font-semibold tracking-tight">{{ title }}</h2>
      <p class="text-sm text-muted-foreground">
        Pedido <span class="font-mono">{{ result.orderRef }}</span>
        <template v-if="result.receipt.tabDisplay"> · Comanda {{ result.receipt.tabDisplay }}</template>
        · {{ result.receipt.totalDisplay }}
      </p>
    </div>

    <!-- TROCO — o herói da tela quando existe. `aria-live` anuncia o valor. -->
    <div v-if="changeDisplay" class="grid justify-items-center gap-1" aria-live="polite" role="status">
      <p class="text-sm font-medium uppercase tracking-wide text-muted-foreground">Troco</p>
      <p class="text-7xl font-bold tabular-nums tracking-tight text-primary md:text-8xl">{{ changeDisplay }}</p>
      <p class="text-sm text-muted-foreground">Confira o troco antes de seguir para a próxima venda.</p>
    </div>

    <!-- Prova digital: QR PIX grande + status vivo do polling, ou o link do
         checkout do cartão (mesmo componente do fluxo de pagamento). -->
    <PosPaymentResult
      v-if="result.payment?.hasProof"
      :proof="result.payment"
      :status="pixStatus"
      :resending="resendingLink"
      large
      class="w-full max-w-md text-left"
      @resend-link="emit('resendLink')"
    />

    <!-- Hierarquia única de ações (mesma disciplina do checkout): UM CTA
         primário; secundárias como botões UNIFORMES do mesmo peso; terciárias
         discretas porém alinhadas no mesmo grupo — nada de botão e link soltos
         disputando a mesma linha. Os handlers são os de sempre (agente do balcão). -->
    <div class="grid justify-items-center gap-3">
      <!-- CTA dominante -->
      <UiButton size="lg" class="h-14 min-w-64 gap-2 text-base" @click="onNewSale">
        {{ pixPending ? "Nova venda mesmo assim" : "Nova venda" }}
        <kbd class="rounded border border-primary-foreground/30 bg-transparent px-1.5 py-0.5 font-mono text-xs font-medium opacity-80" aria-hidden="true">F2</kbd>
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
        <UiButton
          v-if="result.fiscalExpected"
          variant="outline" size="sm" class="gap-1.5"
          :disabled="printingDanfe"
          @click="emit('printDanfe')"
        >
          <Icon name="lucide:printer" class="size-4" />
          Imprimir DANFE
        </UiButton>
        <UiButton variant="outline" size="sm" class="gap-1.5" :href="result.nextUrl">
          <Icon name="lucide:external-link" class="size-4" />
          Abrir no gestor
        </UiButton>
      </div>

      <!-- Terciárias: discretas, alinhadas num único grupo -->
      <div class="flex flex-wrap items-center justify-center gap-2">
        <UiButton
          v-if="result.fiscalExpected && danfeScreenUrl"
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
