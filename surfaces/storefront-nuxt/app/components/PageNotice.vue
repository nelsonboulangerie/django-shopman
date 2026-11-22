<script setup lang="ts">
// O aviso de página (#3242): abaixo das barras do topo, primeiro conteúdo da página, fundo
// sólido e X. Regra do dono para aviso de tela, em todo tamanho. Ver `usePageNotice`.
const route = useRoute()
const { notice, dismiss } = usePageNotice()
const visible = computed(() => !!notice.value && notice.value.path === route.path)

// Sair da página em que o aviso apareceu o tira: ele fala do gesto que acabou de acontecer.
watch(() => route.path, (path, previous) => {
  if (notice.value && previous === notice.value.path && path !== previous) dismiss()
})
</script>

<template>
  <div v-if="visible" class="mx-auto w-full max-w-5xl px-4 pt-4" data-page-notice>
    <UiAlert variant="default" icon="lucide:circle-check" icon-class="text-success" role="status" class="border-success/40 pr-12">
      <UiAlertDescription class="text-foreground">{{ notice!.message }}</UiAlertDescription>
      <UiButton
        variant="ghost"
        size="icon-sm"
        class="absolute right-2 top-2"
        aria-label="Fechar aviso"
        data-page-notice-close
        @click="dismiss"
      >
        <Icon name="lucide:x" class="size-4" />
      </UiButton>
    </UiAlert>
  </div>
</template>
