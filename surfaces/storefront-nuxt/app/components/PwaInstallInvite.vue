<script setup lang="ts">
import type { PwaCopyProjection } from '~/types/shopman'

const props = defineProps<{ copy?: PwaCopyProjection }>()
const route = useRoute()
const {
  canInstall,
  install,
  isStandalone,
  isIos,
  isDismissed,
  markShown,
  dismiss
} = usePwaInstall()
const open = ref(false)
const iosStep = ref<0 | 1>(0)

const excluded = computed(() => isPwaInviteRouteExcluded(route.path))
const eligible = computed(() => Boolean(props.copy)
  && !excluded.value
  && !isStandalone.value
  && !isDismissed.value
  && (canInstall.value || isIos.value))

watch(eligible, (value) => {
  if (!value || open.value) return
  iosStep.value = 0
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

async function installNow () {
  await install()
  open.value = false
}
</script>

<template>
  <BottomSheet
    v-if="copy"
    :open="open"
    :title="isIos ? copy.ios_title.title : copy.install_title.title"
    :description="isIos ? copy.ios_message.message : copy.install_message.message"
    :max-width="isIos ? 'lg' : 'md'"
    :content-class="isIos ? '!max-h-[calc(100dvh-1rem)]' : undefined"
    data-testid="pwa-install-invite"
    @update:open="value => { if (!value) close() }"
  >
    <PwaIosGuide v-if="isIos" v-model:step="iosStep" :copy="copy" />
    <div v-else class="flex items-start gap-3 p-4">
      <span class="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Icon name="lucide:download" class="size-5" />
      </span>
      <p class="pt-1 text-sm text-muted-foreground">{{ copy.install_message.message }}</p>
    </div>

    <template #footer>
      <UiButton
        v-if="isIos && iosStep === 0"
        class="w-full"
        icon="lucide:arrow-right"
        data-testid="ios-next"
        @click="iosStep = 1"
      >
        Próximo
      </UiButton>
      <div v-else-if="isIos" class="grid w-full grid-cols-[auto_1fr] gap-2">
        <UiButton
          variant="outline"
          icon="lucide:arrow-left"
          aria-label="Voltar ao passo 1"
          data-testid="ios-back"
          @click="iosStep = 0"
        >
          Voltar
        </UiButton>
        <UiButton
          icon="lucide:check"
          data-testid="ios-done"
          @click="close"
        >
          {{ copy.ios_done_cta.title }}
        </UiButton>
      </div>
      <UiButton
        v-if="!isIos"
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
