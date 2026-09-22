<script setup lang="ts">
// O convite de instalação da loja.
//
// O COMO deixou de ser copy de servidor e passou a ser fato de plataforma: quem decide
// o texto dos passos é `installPlan()` (`~/utils/installGuide`), por sistema + navegador.
// A copy do Omotenashi continua dona do CONVITE — o título, o benefício e os rótulos de
// botão, que são voz da casa. O passo a passo saiu de lá porque uma chave de copy é uma
// só para todo mundo, e o caminho não é: dizia "Safari" para quem estava no Chrome, no
// Firefox ou dentro do navegador do WhatsApp — e isso não é copy, é erro de fato.
import type { PwaCopyProjection } from '~/types/shopman'

const props = defineProps<{ copy?: PwaCopyProjection }>()
const route = useRoute()
const {
  plan,
  install,
  isStandalone,
  isDismissed,
  markShown,
  dismiss,
  dismissAsDone
} = usePwaInstall()
const open = ref(false)
// UM convite por página: divide a vez com o sheet de novidades (useShopInvite).
const invite = useShopInvite()

const manual = computed(() => plan.value.kind === 'steps')
const excluded = computed(() => isPwaInviteRouteExcluded(route.path))
const eligible = computed(() => Boolean(props.copy)
  && !excluded.value
  && !isStandalone.value
  && !isDismissed.value
  // `invite` é falso onde não há caminho honesto (Firefox de computador, Safari antigo)
  // e onde o caminho existe mas subir sozinho seria adivinhação (Chromium já instalado).
  && plan.value.invite
  && invite.canOpen('pwa-install', route.path))

// Síncrono: a vez fica marcada no mesmo instante em que o convite abre, antes de
// o outro convite reavaliar se pode subir.
watch(open, value => {
  if (value) invite.claim('pwa-install', route.path)
  else invite.release('pwa-install', route.path)
}, { flush: 'sync' })
watch(() => route.path, path => invite.leavePage(path))

watch(eligible, (value) => {
  if (!value || open.value) return
  open.value = true
  markShown()
}, { immediate: true })

watch(excluded, (value) => {
  if (value) open.value = false
})

function close () {
  open.value = false
  dismiss()
}

// Ninguém sabe daqui se ela seguiu os passos — o iOS não avisa. Quem sabe é ela, e
// repetir o convite na semana seguinte gasta a paciência de quem já resolveu.
function finishManual () {
  open.value = false
  dismissAsDone()
}

async function installNow () {
  await install()
  open.value = false
}
</script>

<template>
  <BottomSheet
    v-if="copy"
    :open="open"
    :title="manual ? copy.manual_title.title : copy.install_title.title"
    :description="copy.install_message.message"
    :max-width="manual ? 'lg' : 'md'"
    :content-class="manual ? '!max-h-[calc(100dvh-1rem)]' : undefined"
    data-testid="pwa-install-invite"
    @update:open="value => { if (!value) close() }"
  >
    <PwaInstallSteps v-if="manual" :plan="plan" />
    <div v-else class="flex items-start gap-3 p-4">
      <span class="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Icon name="lucide:download" class="size-5" />
      </span>
      <p class="pt-1 text-sm text-muted-foreground">{{ copy.install_message.message }}</p>
    </div>

    <template #footer>
      <UiButton
        v-if="manual"
        class="w-full"
        icon="lucide:check"
        data-testid="install-done"
        @click="finishManual"
      >
        {{ copy.manual_done_cta.title }}
      </UiButton>
      <UiButton
        v-else
        class="w-full"
        icon="lucide:download"
        @click="installNow"
      >
        {{ copy.install_cta.title }}
      </UiButton>
      <UiButton class="w-full" variant="ghost" @click="close">
        {{ copy.install_dismiss_cta.title }}
      </UiButton>
    </template>
  </BottomSheet>
</template>
