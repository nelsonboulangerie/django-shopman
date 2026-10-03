<script setup lang="ts">
import { isOptimisticLine, LINE_NOTES_MAX_LENGTH, lineNoteCloseIntent } from '~/presentation/cart'
import type { CartItemProjection } from '~/types/shopman'

// Observação de UM item, para quem prepara ("sem gergelim", "bem assado"). Vai
// para a linha da sacola (`meta.notes`) e, pelo pedido, até o ticket do KDS.
// A rota é POR LINHA (`/cart/lines/<line_id>/notes/`): o mesmo SKU pode estar em
// duas linhas com escolhas diferentes, e cada uma tem a sua observação.
//
// O editor é a folha canônica da loja (BottomSheet). Fechar nunca exige salvar:
// X, alça, fundo e Esc fecham na hora, e o texto alterado segue para o servidor
// em segundo plano. Se a gravação falhar, a folha volta aberta com o rascunho
// intacto e o aviso. Jogar fora o que foi escrito pede uma confirmação leve, e
// só quando o texto difere do salvo.
const props = defineProps<{
  line: CartItemProjection
}>()

const { setLineNotes } = useCartState()
const sheetOpen = ref(false)
const draft = ref('')
const saving = ref(false)
const removing = ref(false)
const confirmingDiscard = ref(false)
const errorMessage = ref('')
// Observação a caminho do servidor (salvar por gesto): a linha já a mostra.
const pendingNotes = ref<string | null>(null)

const fieldId = computed(() => `cart-line-note-${props.line.line_id}`)
// Linha otimista ainda não existe no servidor: não há onde gravar.
const writable = computed(() => !isOptimisticLine(props.line))
const savedNotes = computed(() => (props.line.notes || '').trim())
const shownNotes = computed(() => pendingNotes.value ?? savedNotes.value)
const busy = computed(() => saving.value || removing.value)
const dirty = computed(() => draft.value.trim() !== savedNotes.value)

const SAVE_ERROR = 'Não conseguimos salvar a observação. Confira a sua conexão e tente de novo.'
const REMOVE_ERROR = 'Não conseguimos remover a observação. Confira a sua conexão e tente de novo.'

function openEditor () {
  draft.value = shownNotes.value
  errorMessage.value = ''
  confirmingDiscard.value = false
  sheetOpen.value = true
}

function closeEditor () {
  sheetOpen.value = false
  confirmingDiscard.value = false
  errorMessage.value = ''
}

async function persist (notes: string, failure: string) {
  errorMessage.value = ''
  try {
    await setLineNotes(props.line.line_id, notes)
    return true
  } catch {
    errorMessage.value = failure
    confirmingDiscard.value = false
    sheetOpen.value = true
    return false
  }
}

// Fechou por gesto com texto novo: grava em segundo plano e some na hora.
async function saveInBackground () {
  const notes = draft.value.trim()
  pendingNotes.value = notes
  closeEditor()
  try {
    await persist(notes, SAVE_ERROR)
  } finally {
    pendingNotes.value = null
  }
}

async function save () {
  if (busy.value) return
  if (!dirty.value) return closeEditor()
  saving.value = true
  try {
    if (await persist(draft.value.trim(), SAVE_ERROR)) closeEditor()
  } finally {
    saving.value = false
  }
}

async function remove () {
  if (busy.value) return
  removing.value = true
  try {
    if (await persist('', REMOVE_ERROR)) closeEditor()
  } finally {
    removing.value = false
  }
}

function cancel () {
  if (dirty.value) confirmingDiscard.value = true
  else closeEditor()
}

function discard () {
  draft.value = savedNotes.value
  closeEditor()
}

function onSheetOpenChange (value: boolean) {
  // Dois gestos seguidos (Esc e clique no fundo) não podem gravar duas vezes.
  if (value || !sheetOpen.value) return
  // Enquanto o pedido explícito corre, a folha espera a resposta.
  if (busy.value) return
  // Já perguntou se pode jogar fora: o segundo gesto de sair é a resposta.
  if (confirmingDiscard.value) return discard()
  const intent = lineNoteCloseIntent(draft.value, savedNotes.value)
  if (intent === 'save') return saveInBackground()
  if (intent === 'confirm-discard') {
    confirmingDiscard.value = true
    return
  }
  closeEditor()
}
</script>

<template>
  <div v-if="writable" class="mt-2" data-cart-line-note>
    <div v-if="shownNotes" class="flex items-end gap-3">
      <CartLineNoteMark :notes="shownNotes" class="flex-1" />
      <UiButton
        variant="link"
        size="sm"
        class="h-auto shrink-0 p-0"
        :aria-label="`Alterar a observação de ${line.name}`"
        data-cart-line-note-open
        @click="openEditor"
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
      :aria-label="`Escrever uma observação para ${line.name}`"
      data-cart-line-note-open
      @click="openEditor"
    >
      Observação deste item
    </UiButton>

    <BottomSheet
      :open="sheetOpen"
      max-width="md"
      :title="`Observação de ${line.name}`"
      description="Vai junto com o pedido para quem prepara este item."
      data-cart-line-note-sheet
      @update:open="onSheetOpenChange"
    >
      <div class="space-y-2 px-4 py-4">
        <label :for="fieldId" class="sr-only">Observação de {{ line.name }}</label>
        <UiTextarea
          :id="fieldId"
          v-model="draft"
          :rows="3"
          :maxlength="LINE_NOTES_MAX_LENGTH"
          :disabled="busy"
          placeholder="Ex.: sem gergelim, bem assado"
          data-cart-line-note-input
        />
        <p class="text-right shop-meta tabular-nums" aria-live="polite" data-cart-line-note-count>
          {{ draft.length }}/{{ LINE_NOTES_MAX_LENGTH }}
        </p>
        <p v-if="errorMessage" role="alert" class="shop-meta text-destructive" data-cart-line-note-error>
          {{ errorMessage }}
        </p>
        <UiButton
          v-if="savedNotes && !confirmingDiscard"
          variant="ghost"
          size="sm"
          class="-ml-2 text-muted-foreground hover:text-destructive"
          icon="lucide:trash-2"
          :loading="removing"
          :disabled="saving"
          data-cart-line-note-remove
          @click="remove"
        >
          Remover observação
        </UiButton>
      </div>

      <template #footer>
        <div v-if="confirmingDiscard" class="w-full space-y-2" data-cart-line-note-discard>
          <p class="shop-body text-foreground">Descartar o que você escreveu?</p>
          <div class="flex flex-wrap justify-end gap-2">
            <UiButton variant="ghost" data-cart-line-note-discard-confirm @click="discard">
              Descartar
            </UiButton>
            <UiButton data-cart-line-note-keep @click="confirmingDiscard = false">
              Continuar escrevendo
            </UiButton>
          </div>
        </div>
        <div v-else class="flex w-full flex-wrap justify-end gap-2">
          <UiButton variant="ghost" :disabled="busy" data-cart-line-note-cancel @click="cancel">
            Cancelar
          </UiButton>
          <UiButton
            :loading="saving"
            :disabled="removing || !draft.trim()"
            data-cart-line-note-save
            @click="save"
          >
            Salvar observação
          </UiButton>
        </div>
      </template>
    </BottomSheet>
  </div>
</template>
