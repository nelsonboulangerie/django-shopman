<script setup lang="ts">
import type { TrackingPromiseProjection, TrackingCopyProjection } from '~/types/shopman'
import { canSimulatePayment, isHostedCheckout, paymentMethodLabel } from '~/presentation/payment'

// Bloco de pagamento INLINE no acompanhamento (PAYMENT-TRACKING-MERGE). Não é
// mais uma tela: o promise carrega o método e o payload (QR/copia-e-cola/link do
// cartão), e o countdown/poll/SSE vivem na própria página de acompanhamento (o
// prazo do Pix é o `promise.deadline_at`). Aqui só desenhamos o que pagar.
const props = defineProps<{
  promise: TrackingPromiseProjection
  copy: TrackingCopyProjection
  totalDisplay: string
  mockEnabled: boolean
  mockPending: boolean
}>()

const emit = defineEmits<{ (e: 'mock-confirm'): void }>()

// Só depois de o cliente tocar no botão faz sentido dizer "não abriu?".
const tentouAbrirCheckout = ref(false)

const method = computed(() => props.promise.payment_method)
const hasPixCode = computed(() => Boolean(props.promise.pix_qr_code || props.promise.pix_copy_paste))
// Cartão da loja OU link do balcão: os dois abrem a URL do gateway.
const abreCheckout = computed(() => isHostedCheckout(method.value))
const isPix = computed(() => method.value === 'pix')
// Pix ainda sem código não é ação do cliente: pode ser a janela curta de geração
// do gateway, especialmente depois do aceite no `timing=post_commit`.
const esperandoCodigoPix = computed(() => isPix.value && !hasPixCode.value)
// A caixa de captura simulada. A regra mora em presentation/payment.ts, junto
// com a que a página usa para mostrar o bloco — uma pergunta, um dono.
const podeSimular = computed(() => canSimulatePayment({
  payment_method: method.value,
  mock_payment_enabled: props.mockEnabled,
}))

async function copyPix () {
  if (!props.promise.pix_copy_paste || !import.meta.client) return
  await navigator.clipboard.writeText(props.promise.pix_copy_paste)
  useSonner.success(props.copy.pix_copied)
}
</script>

<template>
  <UiCard>
    <UiCardHeader>
      <p class="shop-muted text-sm">{{ copy.total_label }}</p>
      <UiCardTitle>{{ totalDisplay }}</UiCardTitle>
      <UiCardDescription>{{ paymentMethodLabel(method) }}</UiCardDescription>
    </UiCardHeader>
    <UiCardContent class="space-y-4">
      <!-- Cartão ou link: ambiente seguro externo (Stripe). -->
      <div v-if="abreCheckout && promise.checkout_url" class="shop-stack-block rounded-lg border p-4">
        <div class="flex items-start gap-3">
          <Icon name="lucide:shield-check" :size="22" class="mt-0.5 shrink-0 text-emerald-600" />
          <div class="space-y-1">
            <p class="shop-item-title font-semibold text-foreground">Pagamento seguro</p>
            <p class="shop-muted">{{ copy.card_intro }}</p>
            <p class="shop-meta">{{ copy.card_security_note }}</p>
          </div>
        </div>
        <UiButton :href="promise.checkout_url" target="_blank" rel="noopener noreferrer" class="w-full" size="lg" icon="lucide:credit-card" @click="tentouAbrirCheckout = true">
          Pagar com cartão
        </UiButton>
        <p v-if="tentouAbrirCheckout" class="shop-meta text-center">Não abriu? Toque no botão novamente.</p>
      </div>

      <!-- Lugar reservado para o código do Pix (ainda nascendo). -->
      <div v-if="esperandoCodigoPix" class="flex flex-col items-center gap-3 py-2">
        <div class="flex size-48 max-w-full items-center justify-center rounded-lg border border-dashed text-muted-foreground">
          <Icon name="lucide:qr-code" class="size-12 motion-safe:animate-pulse" />
        </div>
        <p class="shop-meta text-center">{{ copy.pix_pending_note }}</p>
      </div>

      <!-- Pix com código: QR + copia-e-cola. O countdown do prazo já é mostrado
           no painel de status (promise.deadline_at). -->
      <div v-if="hasPixCode" class="shop-stack-block">
        <div v-if="promise.pix_qr_code" class="flex flex-col items-center gap-3">
          <div class="rounded-lg border bg-white p-4">
            <img :src="promise.pix_qr_code" alt="QR Code Pix" class="size-48 max-w-full" />
          </div>
          <p class="shop-muted text-center">{{ copy.pix_instruction }}</p>
        </div>

        <div v-if="promise.pix_copy_paste" class="shop-stack-tight">
          <p class="shop-meta">{{ copy.pix_copy_label }}</p>
          <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
            <p
              class="min-w-0 flex-1 cursor-pointer truncate rounded-lg border bg-muted px-3 py-2 font-mono text-xs"
              role="button"
              tabindex="0"
              aria-label="Copiar código Pix"
              :title="promise.pix_copy_paste"
              @click="copyPix"
              @keydown.enter.prevent="copyPix"
              @keydown.space.prevent="copyPix"
            >{{ promise.pix_copy_paste }}</p>
            <UiButton variant="outline" icon="lucide:copy" class="shrink-0" @click="copyPix">{{ copy.pix_copy_btn }}</UiButton>
          </div>
        </div>

        <p class="shop-meta">{{ copy.pix_auto_update_note }}</p>
      </div>

      <!-- Cartão sem página do gateway (payment_mock): sem isto o bloco ficaria
           só com o total, e o testador não saberia o que fazer. -->
      <div v-if="abreCheckout && !promise.checkout_url && podeSimular" class="shop-stack-tight rounded-lg border p-4">
        <div class="flex items-start gap-3">
          <Icon name="lucide:credit-card" :size="22" class="mt-0.5 shrink-0 text-muted-foreground" />
          <p class="shop-muted">Neste ambiente o cartão não abre a página do gateway. Use a captura simulada abaixo.</p>
        </div>
      </div>

      <!-- Ambiente de teste: captura por gateway simulado (DEBUG/staging). -->
      <div v-if="podeSimular" class="shop-stack-tight rounded-lg border border-cta bg-cta/10 p-4">
        <div class="flex items-start gap-3">
          <Icon name="lucide:flask-conical" :size="22" class="mt-0.5 shrink-0 text-cta" />
          <div class="min-w-0">
            <p class="shop-item-title font-semibold text-foreground">Pagamento de teste</p>
            <p class="shop-meta">Use este botão para confirmar o pagamento neste ambiente de teste.</p>
          </div>
        </div>
        <UiButton
          variant="default"
          size="lg"
          class="w-full justify-center bg-cta text-cta-foreground hover:bg-cta/90 hover:text-cta-foreground"
          icon="lucide:flask-conical"
          :loading="mockPending"
          @click="emit('mock-confirm')"
        >
          Simular pagamento
        </UiButton>
      </div>
    </UiCardContent>
  </UiCard>
</template>
