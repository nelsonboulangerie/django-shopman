<script setup lang="ts">
import { CONTINUE_IN_CONVERSATION_SENT, continueInConversationAction, passageErrorMessage } from '~/presentation/cartPassage'
import type { CartConversationStart, CartProjection } from '~/types/shopman'

// "Continuar pelo WhatsApp" (OC-16, C02). Só existe quando o servidor diz que a
// passagem para a conversa é possível agora (X1). O toque pede a mensagem pronta
// (com o código NB, que leva a sacola e não é senha) e abre o WhatsApp. A sacola
// daqui não muda até a Nice receber a mensagem.
const props = defineProps<{ cart: CartProjection }>()

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()

const action = computed(() => continueInConversationAction(props.cart))
const pending = ref(false)
const sent = ref(false)

async function start () {
  if (!action.value || pending.value) return
  pending.value = true
  try {
    const started = await $fetch<CartConversationStart>(apiPath(action.value.href), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include'
    })
    sent.value = true
    if (import.meta.client) window.location.href = started.deep_link
  } catch (error) {
    if (import.meta.client) useSonner.error(passageErrorMessage(error))
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <div v-if="action" class="mt-4 border-t pt-4" data-cart-continue-in-conversation>
    <UiButton
      variant="outline"
      class="w-full"
      icon="lucide:message-circle"
      :loading="pending"
      data-cart-continue-in-conversation-button
      @click="start"
    >
      {{ action.label }}
    </UiButton>
    <p v-if="sent" class="mt-2 shop-body text-muted-foreground" aria-live="polite">
      {{ CONTINUE_IN_CONVERSATION_SENT }}
    </p>
  </div>
</template>
