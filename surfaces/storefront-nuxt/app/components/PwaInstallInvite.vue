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

const excluded = computed(() => isPwaInviteRouteExcluded(route.path))
const eligible = computed(() => Boolean(props.copy)
  && !excluded.value
  && !isStandalone.value
  && !isDismissed.value
  && (canInstall.value || isIos.value))

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
    max-width="md"
    data-testid="pwa-install-invite"
    @update:open="value => { if (!value) close() }"
  >
    <PwaIosGuide v-if="isIos" :copy="copy" />
    <div v-else class="flex items-start gap-3 p-4">
      <span class="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Icon name="lucide:download" class="size-5" />
      </span>
      <p class="pt-1 text-sm text-muted-foreground">{{ copy.install_message.message }}</p>
    </div>

    <template #footer>
      <UiButton
        v-if="isIos"
        class="w-full"
        icon="lucide:check"
        @click="close"
      >
        {{ copy.ios_done_cta.title }}
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
