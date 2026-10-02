<script setup lang="ts">
import { hasOptionGroups } from '~/presentation/productOptions'
import type { ProductMutationMeta, ProductOptionGroup } from '~/types/shopman'
import { claimEarlyTap } from '~/utils/earlyTap'

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
  // Produto com escolhas (sabor, adicionais): o botão abre a folha de opções e
  // nunca vira stepper por SKU (cada combinação é uma linha própria na sacola).
  optionGroups?: ProductOptionGroup[] | null
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
const withOptions = computed(() => hasOptionGroups(props.optionGroups))
const optionsOpen = ref(false)

// O botão nasce ATIVO no HTML do servidor (D1, opção 3). Enquanto o app não montou,
// ele carrega a chave do toque precoce: o script inline do <head> guarda o toque e
// o mostra girando; ao montar, o toque guardado é executado uma vez. Produto
// indisponível não ganha a marca e segue com o `disabled` dele. Ver utils/earlyTap.ts.
const earlyTapKey = computed(() => `cart-add:${props.meta.sku}:${props.addTargetQty ?? 1}`)
const earlyTap = computed(() => (hydrated.value || props.disabled ? undefined : earlyTapKey.value))
const { run: add, pending: adding } = usePendingAction(addOne)

onMounted(() => {
  const replay = !props.disabled && claimEarlyTap(earlyTapKey.value)
  hydrated.value = true
  // O erro já tem aviso próprio no useCartState; aqui só não pode virar rejeição solta.
  if (replay) void add().catch(() => {})
})

async function addOne () {
  if (props.disabled) return
  if (withOptions.value) {
    optionsOpen.value = true
    return
  }
  if (pending.value) return
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
      v-if="qty > 0 && !withOptions"
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
      :data-early-tap="earlyTap"
      :disabled="disabled"
      :loading="pending || adding"
      @click="add"
    />
    <UiButton
      v-else
      variant="default"
      :size="compact ? 'sm' : 'default'"
      icon="lucide:shopping-bag"
      :class="tone === 'inverted' ? 'shop-action-inverted' : ''"
      :data-early-tap="earlyTap"
      :disabled="disabled"
      :loading="pending || adding"
      @click="add"
    >
      {{ addLabel }}
    </UiButton>
    <ProductOptionsSheet
      v-if="withOptions"
      v-model:open="optionsOpen"
      :meta="meta"
      :option-groups="optionGroups || []"
      @added="emit('changed', qty + 1)"
    />
  </span>
</template>
