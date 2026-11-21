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

<style>
/* O "×" do toast DENTRO dele, à direita, no centro da altura, com alvo de 44 px: o
   padrão do X dos avisos de tela. O da biblioteca era um círculo de 20 px pendurado
   FORA do toast, no canto de cima à esquerda, sobre a borda (prévia do #3046). Vale
   para todos os toasts da loja. O toast reserva o lugar do botão à direita, para o
   texto nunca correr por baixo dele. */
[data-sonner-toaster] [data-sonner-toast][data-styled='true']:has([data-close-button]) {
  padding-right: 3.25rem;
}
[data-sonner-toaster] [data-sonner-toast][data-styled='true'] [data-close-button] {
  left: auto;
  right: 0.25rem;
  top: 50%;
  bottom: auto;
  transform: translateY(-50%);
  width: 2.75rem;
  height: 2.75rem;
  border: 0;
  border-radius: 9999px;
  background: transparent;
  color: var(--muted-foreground);
}
[data-sonner-toaster] [data-sonner-toast][data-styled='true'] [data-close-button] svg {
  width: 1rem;
  height: 1rem;
}
[data-sonner-toaster] [data-sonner-toast][data-styled='true']:hover [data-close-button]:hover {
  background: var(--muted);
  color: var(--foreground);
}
</style>
