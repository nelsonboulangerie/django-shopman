<script setup lang="ts">
import type { CartItemProjection, ProductMutationMeta } from '~/types/shopman'

// Pílula de quantidade (padrão iFood): opaca, mesma geometria do botão "+"
// que a origina. Não é campo de formulário — toques entram na fila otimista.
const props = defineProps<{
  meta: ProductMutationMeta
  qty: number
  disabled?: boolean
  maxQty?: number | null
  minQty?: number
  compact?: boolean
  tone?: 'default' | 'inverted'
  // Na sacola, a pílula age sobre a LINHA (`line_id`): com escolhas, o mesmo SKU
  // pode estar em duas linhas, e o PUT por SKU acertaria a errada.
  line?: CartItemProjection
}>()

const emit = defineEmits<{
  changed: [qty: number]
}>()

const { setSkuQty, setLineQty } = useCartState()

const floorQty = computed(() => props.minQty ?? 0)
const atMax = computed(() => props.maxQty != null && props.qty >= props.maxQty)
const atMin = computed(() => props.qty <= floorQty.value)
const removesOnDecrement = computed(() => floorQty.value === 0 && props.qty === 1)

function commit (value: number) {
  const next = clampQuantity(value, props.maxQty, floorQty.value)
  if (next === props.qty) return
  // Rajadas entram na fila serial do carrinho; o estado otimista mantém a UI viva.
  const mutation = props.line ? setLineQty(props.line, next) : setSkuQty(props.meta, next)
  void mutation.then(() => emit('changed', next)).catch(() => {})
}
</script>

<template>
  <div
    role="group"
    :aria-label="`Quantidade de ${meta.name}`"
    class="shop-qty inline-flex h-10 items-center rounded-full border bg-background text-foreground shadow-sm"
    :class="[compact ? '' : 'px-1', tone === 'inverted' ? 'shop-qty-inverted' : '']"
  >
    <UiButton
      variant="ghost"
      size="icon-sm"
      class="size-10 rounded-full text-foreground"
      :icon="removesOnDecrement ? 'lucide:trash-2' : 'lucide:minus'"
      :aria-label="removesOnDecrement ? `Remover ${meta.name}` : `Diminuir ${meta.name}`"
      :disabled="disabled || atMin"
      @click="commit(qty - 1)"
    />
    <span class="min-w-6 text-center text-sm font-semibold tabular-nums" aria-live="polite">{{ qty }}</span>
    <UiButton
      data-quantity-increase
      variant="ghost"
      size="icon-sm"
      class="size-10 rounded-full text-foreground"
      icon="lucide:plus"
      :aria-label="atMax && maxQty != null ? `Máximo disponível de ${meta.name}: ${maxQty}` : `Aumentar ${meta.name}`"
      :title="atMax && maxQty != null ? `Só temos ${maxQty} disponíve${maxQty > 1 ? 'is' : 'l'}` : undefined"
      :disabled="disabled || atMax"
      @click="commit(qty + 1)"
    />
  </div>
</template>
