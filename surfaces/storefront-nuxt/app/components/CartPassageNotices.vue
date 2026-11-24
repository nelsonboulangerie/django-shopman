<script setup lang="ts">
import { openElsewhereNotices, passageErrorMessage } from '~/presentation/cartPassage'
import type { Action, CartProjection } from '~/types/shopman'

// Os avisos da sacola entre a loja e a conversa (OC-16, #3515, #3517), no alto da
// sacola e do Finalizar. Tudo veio da projeção: o que entrou vindo de outro canal
// (e o que mudou, só se mudou) e a sacola aberta no WhatsApp, com "Trazer a sacola
// do WhatsApp" só quando a ação está ligada (X1). Trazer é um gesto só: os itens
// entram aqui, sem pergunta (decisão do dono, 24/11/2026).
const props = defineProps<{ cart: CartProjection }>()
const emit = defineEmits<{ changed: [] }>()

const { runCartPassage } = useCartState()

const notices = computed(() => openElsewhereNotices(props.cart))
const arrival = computed(() => props.cart.transfer_arrival || null)

// O X fecha o aviso desta vez; ele volta ao recarregar enquanto a sacola que chegou
// estiver aberta (a causa dura).
const arrivalClosed = ref(false)
watch(() => arrival.value?.lines.join('|'), () => { arrivalClosed.value = false })

const pending = ref<string>('')

async function run (action: Action) {
  if (pending.value) return
  pending.value = action.ref
  try {
    // Sem aviso flutuante: a confirmação é a própria tela ("Entraram 3 itens…" no
    // alto e os itens na lista). Um toast cobria o item logo abaixo.
    await runCartPassage(action.href, action.payload_schema || {})
    emit('changed')
  } catch (error) {
    if (import.meta.client) useSonner.error(passageErrorMessage(error))
  } finally {
    pending.value = ''
  }
}
</script>

<template>
  <div v-if="(arrival && !arrivalClosed) || notices.length" class="shop-stack-tight" data-cart-passage>
    <UiAlert
      v-if="arrival && !arrivalClosed"
      :variant="arrival.lines.length ? 'warning' : undefined"
      icon="lucide:shopping-bag"
      class="relative pr-12"
      data-cart-transfer-arrival
    >
      <UiAlertTitle class="line-clamp-none leading-snug" data-decisive>{{ arrival.title }}</UiAlertTitle>
      <UiAlertDescription v-if="arrival.lines.length">
        <ul class="mt-1 list-disc space-y-1 pl-4 shop-body">
          <li v-for="line in arrival.lines" :key="line" data-decisive>{{ line }}</li>
        </ul>
      </UiAlertDescription>
      <UiButton
        variant="ghost"
        size="icon"
        icon="lucide:x"
        class="absolute right-1 top-1 size-10"
        aria-label="Fechar aviso"
        data-cart-transfer-arrival-close
        @click="arrivalClosed = true"
      />
    </UiAlert>

    <UiAlert
      v-for="notice in notices"
      :key="notice.channel"
      icon="lucide:message-circle"
      data-cart-open-elsewhere
    >
      <UiAlertTitle class="line-clamp-none leading-snug">{{ notice.text }}</UiAlertTitle>
      <UiAlertDescription v-if="notice.bring">
        <UiButton
          size="sm"
          variant="outline"
          class="mt-2"
          icon="lucide:shopping-bag"
          :loading="pending === notice.bring.ref"
          :disabled="!!pending"
          data-cart-bring
          @click="run(notice.bring)"
        >
          {{ notice.bring.label }}
        </UiButton>
      </UiAlertDescription>
    </UiAlert>
  </div>
</template>
