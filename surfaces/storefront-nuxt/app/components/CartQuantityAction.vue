<script setup lang="ts">
import type { ProductMutationMeta } from '~/types/shopman'

const props = withDefaults(defineProps<{
  meta: ProductMutationMeta
  qty: number
  disabled?: boolean
  maxQty?: number | null
  compact?: boolean
  addLabel?: string
  addTargetQty?: number
  addIconOnly?: boolean
  tone?: 'default' | 'inverted'
}>(), {
  addLabel: 'Adicionar',
  tone: 'default'
})

const emit = defineEmits<{
  changed: [qty: number]
}>()

const { setSkuQty, isPending } = useCartState()
const hydrated = ref(false)
const actionRoot = ref<HTMLElement | null>(null)
const pending = computed(() => isPending(props.meta.sku))

onMounted(() => {
  hydrated.value = true
})

async function addOne () {
  if (!hydrated.value || props.disabled || pending.value) return
  const nextQty = props.addTargetQty ?? 1
  const keepKeyboardFocus = import.meta.client && actionRoot.value?.contains(document.activeElement)
  const mutation = setSkuQty(props.meta, nextQty)
  if (keepKeyboardFocus) {
    await nextTick()
    actionRoot.value?.querySelector<HTMLElement>('[data-quantity-increase]')?.focus()
  }
  try {
    await mutation
    emit('changed', nextQty)
  } catch (error) {
    if (keepKeyboardFocus) {
      await nextTick()
      actionRoot.value?.querySelector<HTMLElement>('button')?.focus()
    }
    throw error
  }
}
</script>

<template>
  <span ref="actionRoot" class="contents">
    <QuantityControl
      v-if="qty > 0"
      :meta="meta"
      :qty="qty"
      :disabled="disabled"
      :max-qty="maxQty"
      :compact="compact"
      :tone="tone"
      @changed="emit('changed', $event)"
    />
    <UiButton
      v-else-if="addIconOnly"
      variant="default"
      size="icon"
      icon="lucide:plus"
      class="size-10 rounded-full shadow-sm"
      :class="tone === 'inverted' ? 'shop-action-inverted' : ''"
      :aria-label="`Adicionar ${meta.name}`"
      :disabled="!hydrated || disabled || pending"
      @click="addOne"
    />
    <UiButton
      v-else
      variant="default"
      :size="compact ? 'sm' : 'default'"
      icon="lucide:shopping-bag"
      :class="tone === 'inverted' ? 'shop-action-inverted' : ''"
      :disabled="!hydrated || disabled || pending"
      :loading="pending"
      @click="addOne"
    >
      {{ addLabel }}
    </UiButton>
  </span>
</template>
