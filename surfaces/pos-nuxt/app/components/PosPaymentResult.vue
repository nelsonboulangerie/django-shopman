<script setup lang="ts">
// Payment proof (spec §2.4 + PCI SAQ A): renders the gateway's digital payment
// data returned by close_sale — the PIX QR + copia-e-cola, or the card checkout
// link. The screen ONLY DISPLAYS this; it never captures card data. The webhook
// is the authoritative confirmation, so the copy is "aguarde confirmação".
import { toast } from "vue-sonner";
import type { PaymentProofView } from "~/presentation/payment";

// `status` = estado do polling PIX vindo do composable: 'polling' (aguardando),
// 'paid' (confirmado), 'expired' (desistiu — terminal/timeout). Cartão/dinheiro
// não pollam → 'idle'. `large` = palco da tela de resultado: QR maior, para o
// cliente escanear de longe.
// `resending` = o reenvio do link está em voo (o composable manda; a tela só
// trava o botão para o clique duplo não virar dois pedidos).
const props = defineProps<{
  proof: PaymentProofView;
  status?: "idle" | "polling" | "paid" | "expired";
  large?: boolean;
  resending?: boolean;
}>();

// O reenvio é um GESTO de rede (Directive nova no servidor), não estado local:
// sobe para quem tem o transporte (usePosSale), como todo comando do balcão.
const emit = defineEmits<{ resendLink: [] }>();

const TONE_CLASS: Record<PaymentProofView["tone"], string> = {
  info: "border-info/30 bg-info/10 text-info",
  warning: "border-warning/30 bg-warning/10 text-amber-800 dark:text-amber-300",
  success: "border-success/30 bg-success/10 text-success",
  danger: "border-destructive/40 bg-destructive/5 text-destructive",
  neutral: "border bg-muted/40",
};

async function copyCode() {
  if (!props.proof.copyPaste) return;
  try {
    await navigator.clipboard.writeText(props.proof.copyPaste);
    toast.success("Código PIX copiado");
  } catch {
    toast.error("Não foi possível copiar. Selecione e copie manualmente.");
  }
}

async function copyLink() {
  if (!props.proof.checkoutUrl) return;
  try {
    await navigator.clipboard.writeText(props.proof.checkoutUrl);
    toast.success("Link copiado — mande para o cliente");
  } catch {
    toast.error("Não foi possível copiar. Selecione e copie manualmente.");
  }
}
</script>

<template>
  <!-- PIX confirmado: o polling detectou o pagamento — troca a tela por "Pago". -->
  <div
    v-if="proof.isPix && status === 'paid'"
    class="grid gap-1 rounded-md border border-success/40 bg-success/10 p-3 text-success dark:text-lime-300"
    role="status"
    aria-live="polite"
  >
    <div class="flex items-center gap-2">
      <Icon name="lucide:circle-check-big" class="size-5" />
      <p class="text-sm font-semibold">Pagamento PIX confirmado · {{ proof.amountDisplay }}</p>
    </div>
  </div>

  <div v-else class="grid gap-3 rounded-md border p-3" :class="TONE_CLASS[proof.tone]">
    <div class="flex items-center gap-2">
      <Icon :name="proof.icon" class="size-5" />
      <div class="min-w-0 flex-1">
        <p class="text-sm font-semibold">{{ proof.isPix ? "Pagamento PIX" : "Link de pagamento" }} · {{ proof.amountDisplay }}</p>
        <!-- No LINK, a mensagem do servidor ("Pagamento criado. Aguarde
             confirmação do gateway antes de tratar como recebido.") é jargão e
             repete o que a linha abaixo já diz. A linha diz o que a casa FAZ
             com a URL (a cadeia WhatsApp → e-mail → SMS enfileirada na venda) e
             deixa a cópia manual como rede, não como gesto padrão. -->
        <p v-if="proof.isLink" class="text-xs opacity-90">Enviando o link ao cliente por WhatsApp, e-mail ou SMS. Se preferir, copie e mande você.</p>
        <p v-else-if="proof.message" class="text-xs opacity-90">{{ proof.message }}</p>
        <!-- Aguardando: gira só ENQUANTO polla. Ao desistir, para de mentir. -->
        <p v-if="proof.isPix && proof.hasProof && status === 'polling'" class="mt-0.5 flex items-center gap-1 text-xs opacity-80">
          <Icon name="lucide:loader-circle" class="size-3 animate-spin" /> Aguardando confirmação do PIX…
        </p>
        <!-- Desistiu (expirado/cancelado): acusa honestamente, sem prometer o que não cumpre. -->
        <p v-else-if="proof.isPix && proof.hasProof && status === 'expired'" class="mt-0.5 flex items-center gap-1 text-xs font-medium text-amber-700 dark:text-amber-400">
          <Icon name="lucide:clock-alert" class="size-3.5" /> Não confirmamos o PIX automaticamente. Confira no gestor ou gere um novo pagamento.
        </p>
      </div>
    </div>

    <!-- PIX: QR + copia-e-cola -->
    <template v-if="proof.isPix && proof.hasProof">
      <img
        v-if="proof.qrCodeSrc"
        :src="proof.qrCodeSrc"
        alt="QR Code PIX"
        class="mx-auto rounded-md border bg-white p-2"
        :class="large ? 'size-64' : 'size-44'"
      >
      <div v-if="proof.copyPaste" class="grid gap-1.5">
        <p class="break-all rounded-md border bg-background/70 px-2.5 py-2 font-mono text-xs">{{ proof.copyPaste }}</p>
        <UiButton variant="outline" size="sm" class="gap-2" @click="copyCode">
          <Icon name="lucide:copy" class="size-4" />
          Copiar código PIX
        </UiButton>
      </div>
    </template>

    <!-- LINK DE PAGAMENTO: para ENTREGAR, não para abrir aqui.
         Ele é a forma do PEDIDO REMOTO — encomenda por telefone, WhatsApp —, e
         nesse pedido o cliente NÃO está no balcão: não há para quem mostrar um
         QR. O gesto real é copiar e mandar pela mesma conversa em que o pedido
         chegou. Abrir a página aqui seria o operador digitando o cartão do
         cliente, o oposto do que a maquininha existe para evitar. -->
    <!-- Uma faixa só: a URL (que ninguém lê — truncada) e o botão que a leva
         embora. Eram três blocos empilhados dizendo a mesma coisa; o gesto é
         um só, e ele cabe numa linha. -->
    <!-- `min-w-0` no próprio contêiner: filho de grid nasce com `min-width:auto`
         e o `truncate` do filho não segura nada — a faixa cresce além do cartão
         e o botão sai pela borda. -->
    <div v-else-if="proof.isLink && proof.checkoutUrl" class="flex min-w-0 items-center gap-2">
      <p class="min-w-0 flex-1 truncate rounded-md border bg-background/70 px-2.5 py-2 font-mono text-xs">{{ proof.checkoutUrl }}</p>
      <UiButton variant="outline" size="sm" class="shrink-0 gap-2" @click="copyLink">
        <Icon name="lucide:copy" class="size-4" />
        Copiar link
      </UiButton>
      <!-- "Não chegou": manda de novo a MESMA URL pela cadeia da casa
           (WhatsApp → e-mail → SMS). O servidor recusa link vencido, pedido
           pago/cancelado e clique cedo demais — a recusa vira toast com o
           motivo, não botão escondido. -->
      <UiButton
        variant="outline"
        size="sm"
        class="shrink-0 gap-2"
        :disabled="resending"
        data-action="resend-link"
        @click="emit('resendLink')"
      >
        <Icon :name="resending ? 'lucide:loader-circle' : 'lucide:send'" class="size-4" :class="resending && 'animate-spin'" />
        Reenviar
      </UiButton>
    </div>

    <!-- Card: hosted checkout link (delegated; no capture here) -->
    <a
      v-else-if="proof.isCard && proof.checkoutUrl"
      :href="proof.checkoutUrl"
      target="_blank"
      rel="noopener"
      class="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition hover:bg-primary/90"
    >
      <Icon name="lucide:external-link" class="size-4" />
      Abrir checkout do cartão
    </a>

    <!-- Até quando o LINK vale — o mesmo relógio do pedido e do gateway, dito
         como o operador diz ao cliente. Sem o prazo na tela, ele não tem o que
         dizer ao telefone, e "o link parou de funcionar" vira ligação. -->
    <p v-if="proof.isLink && proof.expiresDisplay" class="flex items-center gap-1 text-xs opacity-80">
      <Icon name="lucide:clock" class="size-3.5" />
      Pague até {{ proof.expiresDisplay }} para garantir o pedido
    </p>
  </div>
</template>
