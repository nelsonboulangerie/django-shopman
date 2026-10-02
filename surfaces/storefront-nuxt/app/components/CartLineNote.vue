<script setup lang="ts">
import { isOptimisticLine } from '~/presentation/cart'
import type { CartItemProjection } from '~/types/shopman'

// Observação de UM item, para a cozinha ("sem gergelim", "bem assado"). Vai
// para a linha da sacola (`meta.notes`) e, pelo pedido, até o ticket do KDS.
// Discreta de propósito: a maioria das linhas não tem observação, e o convite
// não pode competir com a quantidade nem com o preço.
const LINE_NOTES_MAX_LENGTH = 280

const props = defineProps<{
  line: CartItemProjection
}>()

const { setLineNotes } = useCartState()
const editing = ref(false)
const draft = ref('')
const saving = ref(false)
const fieldId = computed(() => `cart-line-note-${props.line.sku}`)
// Linha otimista ainda não existe no servidor: não há onde gravar.
const writable = computed(() => !isOptimisticLine(props.line))

function open () {
  draft.value = props.line.notes || ''
  editing.value = true
}

function cancel () {
  editing.value = false
  draft.value = ''
}

async function save () {
  if (saving.value) return
  saving.value = true
  try {
    await setLineNotes(props.line.sku, draft.value.trim())
    editing.value = false
  } catch {
    if (import.meta.client) useSonner.error('Não conseguimos salvar a observação. Tente de novo.')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div v-if="writable" class="mt-2" data-cart-line-note>
    <div v-if="editing" class="space-y-2">
      <label :for="fieldId" class="shop-meta text-foreground">Observação deste item</label>
      <UiTextarea
        :id="fieldId"
        v-model="draft"
        :rows="2"
        :maxlength="LINE_NOTES_MAX_LENGTH"
        placeholder="Ex.: sem gergelim, bem assado"
        autofocus
        data-cart-line-note-input
      />
      <div class="flex flex-wrap items-center gap-2">
        <UiButton size="sm" :loading="saving" data-cart-line-note-save @click="save">
          Salvar observação
        </UiButton>
        <UiButton size="sm" variant="ghost" :disabled="saving" @click="cancel">
          Cancelar
        </UiButton>
        <span class="ml-auto shop-meta tabular-nums" aria-live="polite">{{ draft.length }}/{{ LINE_NOTES_MAX_LENGTH }}</span>
      </div>
    </div>

    <div v-else-if="line.notes" class="flex items-start gap-2">
      <p class="min-w-0 flex-1 shop-meta text-foreground" data-cart-line-note-text>
        <Icon name="lucide:message-square-text" class="mr-1 inline size-3.5 align-text-bottom" />
        Obs.: {{ line.notes }}
      </p>
      <UiButton
        variant="link"
        size="sm"
        class="h-auto p-0"
        :aria-label="`Alterar a observação de ${line.name}`"
        @click="open"
      >
        Alterar
      </UiButton>
    </div>

    <UiButton
      v-else
      variant="link"
      size="sm"
      class="h-auto p-0 text-muted-foreground"
      icon="lucide:message-square-plus"
      data-cart-line-note-open
      @click="open"
    >
      Observação deste item
    </UiButton>
  </div>
</template>
