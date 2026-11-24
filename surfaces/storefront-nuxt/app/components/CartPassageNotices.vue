<script setup lang="ts">
import { openElsewhereNotices, passageErrorMessage } from '~/presentation/cartPassage'
import type { Action, CartProjection } from '~/types/shopman'

// Os avisos da sacola entre a loja e a conversa (OC-16, #3515, #3517), no alto da
// sacola e do Finalizar. Tudo o que aparece aqui veio da projeção: a pergunta
// "substituir ou manter", as diferenças da sacola que chegou e a sacola aberta em
// outro canal, com "Trazer para cá" só quando a ação está ligada (X1).
const props = defineProps<{ cart: CartProjection }>()
const emit = defineEmits<{ changed: [] }>()

const { runCartPassage } = useCartState()

const notices = computed(() => openElsewhereNotices(props.cart))
const conflict = computed(() => props.cart.transfer_conflict || null)
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
    // Sem aviso flutuante: a confirmação é a própria tela (a sacola que chegou e, com
    // diferenças, o aviso âmbar no alto). Um toast cobria o item logo abaixo.
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
  <div v-if="conflict || (arrival && !arrivalClosed) || notices.length" class="shop-stack-tight" data-cart-passage>
    <UiAlert v-if="conflict" variant="warning" icon="lucide:shopping-bag" data-cart-transfer-conflict>
      <UiAlertTitle class="line-clamp-none leading-snug">{{ conflict.title }}</UiAlertTitle>
      <UiAlertDescription>
        <p class="shop-body">{{ conflict.message }}</p>
        <div class="mt-3 flex flex-wrap gap-2">
          <UiButton
            size="sm"
            :loading="pending === conflict.replace.ref"
            :disabled="!!pending"
            data-cart-transfer-replace
            @click="run(conflict.replace)"
          >
            {{ conflict.replace.label }}
          </UiButton>
          <UiButton
            size="sm"
            variant="outline"
            :loading="pending === conflict.keep.ref"
            :disabled="!!pending"
            data-cart-transfer-keep
            @click="run(conflict.keep)"
          >
            {{ conflict.keep.label }}
          </UiButton>
        </div>
      </UiAlertDescription>
    </UiAlert>

    <UiAlert v-if="arrival && !arrivalClosed" variant="warning" icon="lucide:arrow-right-left" class="relative pr-12" data-cart-transfer-arrival>
      <UiAlertTitle class="line-clamp-none leading-snug">{{ arrival.title }}</UiAlertTitle>
      <UiAlertDescription>
        <ul class="mt-1 list-disc space-y-1 pl-4 shop-body">
          <li v-for="line in arrival.lines" :key="line" data-decisive>{{ line }}</li>
        </ul>
        <p v-if="arrival.total_line" class="mt-2 shop-body font-semibold" data-decisive>{{ arrival.total_line }}</p>
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
      <UiAlertDescription>
        <p class="shop-body">{{ notice.consequence }}</p>
        <UiButton
          v-if="notice.bring"
          size="sm"
          variant="outline"
          class="mt-3"
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
