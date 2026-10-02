<script setup lang="ts">
// Folha de escolhas do produto (Fase 1): sabor obrigatório, adicionais com preço.
// Um bloco por grupo, com a regra dita em palavras ("Escolha 1", "Opcional, até 2").
// O preço do rodapé é o do produto mais as escolhas, ao vivo; "Adicionar" só acende
// com os mínimos cumpridos. A loja manda só `{group, ref}`: preço e nome o servidor
// relê do catálogo. Erros seguem a fila da sacola: 409 sobe o SubstituteSheet
// global (esta folha fecha para não empilhar), escolha recusada (400) aparece aqui.
import {
  firstMissingOptionHint,
  initialOptionsState,
  isOptionLocked,
  isOptionSelected,
  isSingleChoice,
  optionGroupRule,
  optionPriceLabel,
  optionsPayload,
  optionsSelectionValid,
  optionsTotalQ,
  toggleOption,
  type OptionSelectionState
} from '~/presentation/productOptions'
import { formatCentavos } from '~/presentation/cart'
import type { ProductMutationMeta, ProductOptionGroup } from '~/types/shopman'

const props = defineProps<{
  open: boolean
  meta: ProductMutationMeta
  optionGroups: ProductOptionGroup[]
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  added: []
}>()

const { addLineWithOptions } = useCartState()

const selection = ref<OptionSelectionState>(initialOptionsState(props.optionGroups))
const submitting = ref(false)
const optionError = ref('')

// Cada abertura começa do zero: a folha é um pedido novo, não um rascunho.
watch(() => props.open, open => {
  if (!open) return
  selection.value = initialOptionsState(props.optionGroups)
  optionError.value = ''
})

const valid = computed(() => optionsSelectionValid(selection.value, props.optionGroups))
const totalDisplay = computed(() => formatCentavos(optionsTotalQ(props.meta.price_q, selection.value, props.optionGroups)))
const missingHint = computed(() => firstMissingOptionHint(selection.value, props.optionGroups))

function toggle (group: ProductOptionGroup, optionRef: string) {
  selection.value = toggleOption(selection.value, group, optionRef)
  optionError.value = ''
}

function setOpen (value: boolean) {
  if (submitting.value && !value) return
  emit('update:open', value)
}

async function submit () {
  if (!valid.value || submitting.value) return
  submitting.value = true
  optionError.value = ''
  try {
    await addLineWithOptions(props.meta, 1, optionsPayload(selection.value, props.optionGroups))
    emit('update:open', false)
    emit('added')
    if (import.meta.client) useSonner.success(`Adicionamos ${props.meta.name} à sua sacola.`)
  } catch (error) {
    const { status, data } = httpError(error)
    if (status === 409) {
      // O SubstituteSheet global assume (substitutos, "Levar N", "Me avise").
      emit('update:open', false)
    } else if (status === 400) {
      optionError.value = String(data?.detail || 'Revise as escolhas deste item.')
    }
    // Demais erros: o aviso já saiu pela fila da sacola; a folha fica aberta.
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <BottomSheet
    :open="open"
    max-width="md"
    :title="meta.name"
    description="Escolha como quer o seu pedido."
    data-product-options-sheet
    @update:open="setOpen"
  >
    <div class="shop-stack-block px-4 py-4">
      <fieldset
        v-for="group in optionGroups"
        :key="group.ref"
        class="space-y-2"
        :data-product-option-group="group.ref"
      >
        <legend class="flex w-full items-baseline justify-between gap-3 pb-1">
          <span class="shop-item-title">{{ group.label }}</span>
          <span class="shop-meta" data-product-option-rule>{{ optionGroupRule(group) }}</span>
        </legend>
        <div class="space-y-2" :role="isSingleChoice(group) ? 'radiogroup' : 'group'" :aria-label="group.label">
          <UiButton
            v-for="option in group.options"
            :key="option.ref"
            variant="outline"
            :role="isSingleChoice(group) ? 'radio' : 'checkbox'"
            :aria-checked="isOptionSelected(selection, group.ref, option.ref)"
            :disabled="isOptionLocked(selection, group, option.ref) || submitting"
            class="h-auto min-h-12 w-full justify-start gap-3 whitespace-normal rounded-lg px-3 py-2 text-left font-normal"
            :class="isOptionSelected(selection, group.ref, option.ref) ? 'border-primary bg-primary/5 hover:bg-primary/10' : ''"
            :data-product-option="option.ref"
            @click="toggle(group, option.ref)"
          >
            <Icon
              :name="isOptionSelected(selection, group.ref, option.ref)
                ? (isSingleChoice(group) ? 'lucide:circle-dot' : 'lucide:square-check')
                : (isSingleChoice(group) ? 'lucide:circle' : 'lucide:square')"
              class="size-5 shrink-0"
              :class="isOptionSelected(selection, group.ref, option.ref) ? 'text-primary' : 'text-muted-foreground'"
            />
            <span class="min-w-0 flex-1 shop-body">{{ option.label }}</span>
            <span v-if="!option.available" class="shrink-0 shop-meta" data-product-option-unavailable>Indisponível</span>
            <span v-else-if="option.price_q > 0" class="shrink-0 shop-meta tabular-nums text-foreground">{{ optionPriceLabel(option.price_q) }}</span>
          </UiButton>
        </div>
      </fieldset>

      <p v-if="optionError" role="alert" class="text-sm text-destructive" data-product-options-error>{{ optionError }}</p>
    </div>

    <template #footer>
      <div class="flex w-full items-center justify-between gap-3">
        <div class="min-w-0">
          <p class="shop-price-strong tabular-nums" aria-live="polite" data-product-options-total>{{ totalDisplay }}</p>
          <p v-if="missingHint" class="shop-meta" data-product-options-missing>{{ missingHint }}</p>
        </div>
        <UiButton
          icon="lucide:shopping-bag"
          :disabled="!valid"
          :loading="submitting"
          data-product-options-add
          @click="submit"
        >
          Adicionar
        </UiButton>
      </div>
    </template>
  </BottomSheet>
</template>
