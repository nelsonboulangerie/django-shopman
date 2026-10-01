<script setup lang="ts">
// Aviso de versão nova do app instalado. Porte do `OperatorPwaUpdatePrompt` do kit.
//
// PERSISTENTE, não toast: fica na tela enquanto houver worker novo em espera. O que
// havia antes era um toast de tiro único com botão de fechar; um toque no X (ou um
// pedido em andamento) e o cliente instalado não via outra oferta até fechar todas as
// janelas do app, o que no iOS pode levar dias.
//
// Nunca aplica sozinho: a versão nova só entra pelo toque em "Atualizar". Some nas
// telas em que a recarga perderia algo em curso (checkout, pedido, login) e sem rede,
// e volta na tela seguinte. A sonda que faz o aviso aparecer mora aqui também, para
// que `app.vue` e `error.vue` tenham as duas coisas montando um componente só.
import type { PwaCopyProjection } from '~/types/shopman'
import { shouldShowPwaUpdatePrompt } from '~/presentation/pwaRuntime'

const props = defineProps<{ copy?: PwaCopyProjection }>()

const route = useRoute()
const online = useOnline()
const pwa = usePwaUpdate()
usePwaUpdateCheck()

const updating = ref(false)
const title = computed(() => props.copy?.update_title.title || 'Nova versão disponível')
const cta = computed(() => props.copy?.update_cta.title || 'Atualizar')
const visible = computed(() => updating.value || shouldShowPwaUpdatePrompt({
  needsRefresh: pwa.needRefresh.value,
  online: online.value,
  path: route.path
}))

async function update () {
  if (updating.value) return
  updating.value = true
  const accepted = await pwa.update()
  if (!accepted) updating.value = false
}
</script>

<template>
  <Transition
    enter-active-class="transition duration-200 ease-out"
    enter-from-class="translate-y-2 opacity-0"
    leave-active-class="transition duration-150 ease-in"
    leave-to-class="translate-y-2 opacity-0"
  >
    <aside
      v-if="visible"
      aria-live="polite"
      data-testid="pwa-update-prompt"
      data-focus-obstruction
      class="fixed inset-x-0 bottom-[calc(4rem+env(safe-area-inset-bottom))] z-50 px-4 md:bottom-4"
    >
      <div class="mx-auto flex max-w-md items-center gap-3 rounded-lg border bg-popover p-3 text-popover-foreground shadow-lg">
        <Icon name="lucide:sparkles" class="size-4 shrink-0 text-primary" aria-hidden="true" />
        <p class="min-w-0 flex-1 text-sm font-semibold">{{ title }}</p>
        <UiButton size="sm" :loading="updating" :disabled="updating" @click="update">
          {{ cta }}
        </UiButton>
      </div>
    </aside>
  </Transition>
</template>
