<template>
  <Toaster
    class="toaster group"
    :visible-toasts="5"
    close-button
    :duration="7000"
    :theme="sonnerTheme"
    :offset="{ bottom: `${obstruction + 24}px` }"
    :mobile-offset="{ bottom: `${obstruction + 16}px` }"
    :style="{
      '--normal-bg': 'var(--popover)',
      '--normal-text': 'var(--popover-foreground)',
      '--normal-border': 'var(--border)',
    }"
    :toast-options="{
      class: 'items-start!',
      classes: {
        icon: 'mt-0.5',
        toast:
          'group toast group-[.toaster]:bg-background group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg',
        description: 'group-[.toast]:text-muted-foreground',
        actionButton: 'group-[.toast]:bg-primary group-[.toast]:text-primary-foreground',
        cancelButton: 'group-[.toast]:bg-muted group-[.toast]:text-muted-foreground',
      },
    }"
  />
</template>

<script setup lang="ts">
const colorMode = useColorMode()
const sonnerTheme = computed(() => colorMode.value === 'dark' ? 'dark' : 'light')
// O toast fica embaixo (o lugar natural no celular), mas ACIMA de tudo que flutua na
// base: barra de navegação, card do total, barra de ação, folha aberta (#3046). Antes
// ele caía a 16 px da borda, por cima da barra de baixo, com o texto ilegível sobre
// "Início" e "Cardápio". A folga de sempre (24 px no desktop, 16 no celular) vale a
// partir do topo do que flutua.
const obstruction = useBottomObstruction()
</script>
