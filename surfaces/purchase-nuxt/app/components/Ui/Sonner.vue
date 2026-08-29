<template>
  <Toaster
    class="toaster group"
    position="top-center"
    rich-colors
    :visible-toasts="3"
    close-button
    :duration="7000"
    :theme="sonnerTheme"
    :style="{
      '--normal-bg': 'var(--popover)',
      '--normal-text': 'var(--popover-foreground)',
      '--normal-border': 'var(--border)',
      '--success-bg': 'var(--success)',
      '--success-text': 'var(--success-foreground)',
      '--success-border': 'var(--success)',
      '--error-bg': 'var(--destructive)',
      '--error-text': 'var(--destructive-foreground)',
      '--error-border': 'var(--destructive)',
      '--warning-bg': 'var(--warning)',
      '--warning-text': 'var(--warning-foreground)',
      '--warning-border': 'var(--warning)',
    }"
    :toast-options="{
      class: 'items-start!',
      classes: {
        icon: 'mt-0.5',
        toast: 'group toast group-[.toaster]:shadow-lg',
        actionButton: 'group-[.toast]:bg-background/20 group-[.toast]:text-current group-[.toast]:font-semibold',
        cancelButton: 'group-[.toast]:bg-background/20 group-[.toast]:text-current',
      },
    }"
  />
</template>

<script setup lang="ts">
/**
 * O aviso da tela de Compras — em cima, e com cor.
 *
 * Duas correções contra o mesmo sintoma ("o aviso? não vi"):
 *
 * 1. **`top-center`, não o rodapé.** O padrão do Sonner é o canto inferior, e
 *    no celular esta tela tem barra de navegação fixa em `bottom-0`: o aviso
 *    nascia embaixo dela, fora do olhar de quem acabou de apertar um botão que
 *    também estava no fim de uma página longa.
 * 2. **`rich-colors`.** As classes forçavam `bg-background`/`text-foreground`
 *    em TODO toast, então erro e sucesso saíam com a mesma cara cinza. Os
 *    tokens do tema operador entram como fundo sólido (verde-folha/tijolo com
 *    a `foreground` do par), e a cor volta a significar o que aconteceu.
 */
const colorMode = useColorMode();
const sonnerTheme = computed(() => colorMode.value === "dark" ? "dark" : "light");
</script>
