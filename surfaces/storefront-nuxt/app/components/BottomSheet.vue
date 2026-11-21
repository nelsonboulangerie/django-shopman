<script setup lang="ts">
// Bottom-sheet canônico da loja: um único figurino para todos os painéis que sobem
// da base no mobile (etiqueta de endereço, formulário de endereço, mapa, confirmação
// e recibo do pedido). Padroniza superfície, centragem, largura, header com folga
// do X, rodapé e a affordance de fechar — o corpo continua livre via slot default.
//
// Superfície NEUTRA (card branco / muted cinza); a cor da marca fica nos CTAs que o
// chamador coloca no rodapé. Construído sobre a primitiva Reka (UiSheet) — foco,
// Esc, scroll-lock e backdrop vêm dela.
import type { HTMLAttributes } from 'vue'

// data-* e afins (usados por testes/seletores) vão para o elemento de conteúdo.
defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<{
  open: boolean
  title?: string
  description?: string
  /** Largura máxima do painel (centralizado). */
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl'
  /** Superfície neutra: `card` (branco, padrão) ou `muted` (cinza claro). */
  surface?: 'card' | 'muted'
  /** Classe extra mesclada no conteúdo (ex.: altura fixa do mapa). */
  contentClass?: HTMLAttributes['class']
}>(), {
  maxWidth: 'xl',
  surface: 'card'
})

const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const maxWidthClass = computed(() => ({
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl'
})[props.maxWidth])

const surfaceClass = computed(() =>
  props.surface === 'card' ? 'bg-card text-card-foreground' : 'bg-muted'
)
// Gradiente de scroll: precisa desbotar PARA a cor da superfície (branco/cinza),
// senão a borda do fade fica visível.
const fadeFromClass = computed(() => props.surface === 'card' ? 'from-card' : 'from-muted')

// "Tem mais abaixo" do corpo rolável: o mesmo `<MoreBelow />` da página, no modo
// caixa (#2414). A regra de que a folga do fim não conta é dele agora.
const scrollEl = ref<HTMLElement>()

// Teclado virtual: o painel é `fixed`, e o teclado do iOS/Android não encolhe o
// layout viewport ao qual ele se ancora — sem compensar, o sheet fica POR BAIXO
// do teclado e o campo vira digitação às cegas. `panelStyle` sobe o painel para
// o topo do teclado e limita a altura ao que sobrou de visual viewport; sem
// teclado, ele só soma a barra de gestos (iPhone X) à folga da base.
const { overlap: keyboardInset, panelStyle } = useVirtualKeyboard(() => props.open)

// O campo focado precisa continuar à vista quando a altura útil encolhe. É o
// corpo rolável que se ajusta (`block: 'nearest'`), nunca a página inteira.
function revealFocused () {
  if (!import.meta.client) return
  const active = document.activeElement as HTMLElement | null
  if (!active || !scrollEl.value?.contains(active)) return
  // O toque na dica "tem mais abaixo" foca o botão dela, e trazer ESSE foco à vista
  // cancelava a rolagem suave até o fim que o próprio toque pediu (#2414).
  if (active.closest('[data-more-below]')) return
  active.scrollIntoView({ block: 'nearest' })
}
function onFocusIn () {
  if (import.meta.client) requestAnimationFrame(revealFocused)
}
watch(keyboardInset, () => {
  if (import.meta.client) requestAnimationFrame(revealFocused)
})
</script>

<template>
  <UiSheet :open="open" @update:open="value => emit('update:open', value)">
    <UiSheetContent
      side="bottom"
      variant="floating"
      :class="['mx-auto flex max-h-[85dvh] w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden p-0', maxWidthClass, surfaceClass, contentClass]"
      v-bind="$attrs"
      :style="panelStyle"
      @focusin="onFocusIn"
    >
      <!-- X sempre visível e bem posicionado (a primitiva renderia um botão vazio). -->
      <template #close>
        <UiSheetX sr-text="Fechar" />
      </template>

      <!-- Alça de arraste: affirma o idiom de sheet e dá acabamento mobile-native. -->
      <div
        class="mx-auto mt-2 h-1.5 w-9 shrink-0 rounded-full bg-muted-foreground/20"
        aria-hidden="true"
      />

      <UiSheetHeader
        v-if="title || $slots.header"
        class="shrink-0 gap-1 border-b px-4 pt-3 pb-4 pr-12 text-left"
      >
        <slot name="header">
          <UiSheetTitle :title="title" />
          <UiSheetDescription v-if="description" :description="description" />
        </slot>
      </UiSheetHeader>

      <!-- Corpo rolável: flex até o fim (nunca `h-full`/altura %). A altura do
           wrapper vem do flex-grow do pai; uma altura percentual não resolve
           contra base flex e desaba para a altura do conteúdo — o corpo deixaria
           de recortar/rolar e vazaria POR CIMA do rodapé. -->
      <div class="relative flex min-h-0 flex-1 flex-col">
        <div ref="scrollEl" class="min-h-0 flex-1 overflow-y-auto">
          <slot />
          <MoreBelow contained :container="scrollEl" :fade-from="fadeFromClass" />
        </div>
      </div>

      <UiSheetFooter
        v-if="$slots.footer"
        class="shrink-0 gap-2 border-t p-4"
      >
        <slot name="footer" />
      </UiSheetFooter>
    </UiSheetContent>
  </UiSheet>
</template>
