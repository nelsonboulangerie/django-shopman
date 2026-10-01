<script setup lang="ts">
// Versão nova do app instalado: a loja FORÇA (decisão do dono, D9, 01/10/2026).
//
// Duas portas, decididas em `presentation/pwaRuntime.ts`:
//   1. Navegar entre telas, com versão nova em espera, recarrega a página no destino.
//   2. Fora das telas protegidas, um aviso BLOQUEIA a tela: sem fechar, sem Esc, com
//      um único botão, "Atualizar".
//
// NUNCA durante o pagamento. No checkout, no pedido e no login nada recarrega e nada
// bloqueia: o cliente pode estar digitando endereço, pagando ou digitando o código de
// acesso, e a recarga perderia isso. A versão nova entra na primeira tela seguinte que
// não for protegida (`pwaUpdateRouteProtected`). Sem rede também não: a página
// recarregada cairia no casco offline.
//
// A sonda que faz a versão nova aparecer mora aqui também, para que `app.vue` e
// `error.vue` tenham tudo montando um componente só.
import type { PwaCopyProjection } from '~/types/shopman'
import {
  shouldApplyPwaUpdateOnNavigation,
  shouldBlockForPwaUpdate
} from '~/presentation/pwaRuntime'

const props = defineProps<{ copy?: PwaCopyProjection }>()

const route = useRoute()
const router = useRouter()
const online = useOnline()
const pwa = usePwaUpdate()
usePwaUpdateCheck()

const updating = ref(false)
const title = computed(() => props.copy?.update_title.title || 'A loja tem uma versão nova')
const message = computed(() => props.copy?.update_title.message || 'Atualize para continuar. Sua sacola fica guardada.')
const cta = computed(() => props.copy?.update_cta.title || 'Atualizar')
const blocking = computed(() => updating.value || shouldBlockForPwaUpdate({
  needsRefresh: pwa.needRefresh.value,
  online: online.value,
  path: route.path
}))

/** Aplica a versão nova: o worker assume e a página recarrega onde está. Uma vez só. */
async function update () {
  if (updating.value) return
  updating.value = true
  const accepted = await pwa.update()
  if (!accepted) updating.value = false
}

// Porta 1: a navegação já trocou de tela no cliente; aplicar agora recarrega a página
// no DESTINO (o worker recarrega a URL corrente quando assume).
const removeNavigationHook = router.afterEach((to, from) => {
  if (shouldApplyPwaUpdateOnNavigation({
    needsRefresh: pwa.needRefresh.value,
    online: online.value,
    from: from.path,
    to: to.path
  })) void update()
})
onBeforeUnmount(removeNavigationHook)

// Porta 2: o aviso bloqueia de verdade. Scroll travado e o resto da loja inerte para
// teclado e leitor de tela; Esc não fecha (não há o que fechar).
const panel = useTemplateRef<HTMLElement>('panel')
useOverlayLock(blocking, {
  inert: ['.shop-shell', '.shop-bottomnav-bar'],
  focus: panel
})
</script>

<template>
  <Transition
    enter-active-class="transition duration-200 ease-out"
    enter-from-class="opacity-0"
    leave-active-class="transition duration-150 ease-in"
    leave-to-class="opacity-0"
  >
    <div
      v-if="blocking"
      data-testid="pwa-update-prompt"
      class="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 px-4 pb-[env(safe-area-inset-bottom)]"
    >
      <section
        ref="panel"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="pwa-update-title"
        aria-describedby="pwa-update-message"
        tabindex="-1"
        class="w-full max-w-sm rounded-lg border bg-popover p-6 text-center text-popover-foreground shadow-lg"
      >
        <Icon name="lucide:sparkles" class="mx-auto size-6 text-primary" aria-hidden="true" />
        <h2 id="pwa-update-title" class="mt-3 text-base font-semibold">{{ title }}</h2>
        <p id="pwa-update-message" class="mt-1 text-sm text-muted-foreground">{{ message }}</p>
        <UiButton class="mt-4 w-full" :loading="updating" :disabled="updating" @click="update">
          {{ cta }}
        </UiButton>
      </section>
    </div>
  </Transition>
</template>
