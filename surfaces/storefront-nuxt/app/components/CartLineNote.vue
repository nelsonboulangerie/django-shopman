<script setup lang="ts">
// Observação por item da sacola ("sem cebola"). Grava em meta.notes da linha,
// a mesma chave do PDV, e chega ao ticket da cozinha. A observação do pedido
// inteiro (interfone, troco) continua na finalização.
const NOTES_MAX_LENGTH = 280

const props = defineProps<{
  lineId: string
  name: string
  notes?: string
  disabled?: boolean
}>()

const { setLineNotes } = useCartState()
const editing = ref(false)
const draft = ref('')
const fieldId = computed(() => `cart-line-note-${props.lineId}`)
const saved = computed(() => (props.notes || '').trim())

function open () {
  draft.value = saved.value
  editing.value = true
}

function cancel () {
  editing.value = false
  draft.value = ''
}

const { run: save, pending: saving } = usePendingAction(async () => {
  const text = draft.value.trim().slice(0, NOTES_MAX_LENGTH)
  try {
    await setLineNotes(props.lineId, text)
    editing.value = false
    if (import.meta.client) {
      useSonner(text ? 'Observação salva.' : 'Observação removida.')
    }
  } catch {
    if (import.meta.client) useSonner.error('Não conseguimos salvar a observação. Tente de novo.')
  }
})
</script>

<template>
  <div class="mt-2" data-cart-line-note>
    <div v-if="editing" class="space-y-2">
      <UiLabel :for="fieldId" class="text-xs font-semibold">
        Observação
      </UiLabel>
      <UiTextarea
        :id="fieldId"
        v-model="draft"
        :rows="2"
        :maxlength="NOTES_MAX_LENGTH"
        placeholder="Ex.: sem cebola"
        data-cart-line-note-input
      />
      <div class="flex items-center justify-end gap-2">
        <span class="mr-auto text-xs text-muted-foreground tabular-nums">{{ draft.length }}/{{ NOTES_MAX_LENGTH }}</span>
        <UiButton size="sm" variant="ghost" :disabled="saving" @click="cancel">
          Cancelar
        </UiButton>
        <UiButton size="sm" :loading="saving" data-cart-line-note-save @click="save()">
          Salvar observação
        </UiButton>
      </div>
    </div>
    <div v-else-if="saved" class="flex items-start gap-2">
      <p class="min-w-0 flex-1 shop-meta text-foreground" data-cart-line-note-text>
        <Icon name="lucide:message-square-text" class="mr-1 inline size-3.5 align-[-2px]" />
        {{ saved }}
      </p>
      <UiButton
        size="sm"
        variant="link"
        class="h-auto shrink-0 p-0 text-xs"
        :disabled="disabled"
        :aria-label="`Alterar a observação de ${name}`"
        @click="open"
      >
        Alterar
      </UiButton>
    </div>
    <UiButton
      v-else
      size="sm"
      variant="link"
      class="h-auto p-0 text-xs text-muted-foreground"
      icon="lucide:message-square-plus"
      :disabled="disabled"
      :aria-label="`Adicionar observação em ${name}`"
      data-cart-line-note-open
      @click="open"
    >
      Adicionar observação
    </UiButton>
  </div>
</template>
