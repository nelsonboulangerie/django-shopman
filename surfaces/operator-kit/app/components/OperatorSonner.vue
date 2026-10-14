<script setup lang="ts">
// Aviso passageiro da suíte (vue-sonner). Cada tom pinta o aviso com o par do tema
// (`--success`/`--success-foreground`, `--destructive`, `--warning`, `--info`) e a ação
// dentro dele acompanha a cor do aviso (D8): contorno na cor do texto do aviso, fundo
// do próprio aviso. O texto da ação é o mesmo par do aviso, então o contraste dela é o
// do aviso, AA nos dois temas (`tests/toastContrast.test.ts`).
//
// As classes da ação levam `!`: a folha do vue-sonner fica fora de `@layer` e vence
// qualquer utilitário do Tailwind sem ele, por mais específico que seja. Sem `!` o botão
// saía no par neutro (`--popover-foreground`), escuro sobre qualquer cor de aviso. A
// trava que mede o estilo computado no navegador é `tests/catalog/toast-action.spec.ts`.
const colorMode = useColorMode();
const sonnerTheme = computed(() => colorMode.value === "dark" ? "dark" : "light");
</script>

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
      '--info-bg': 'var(--info)',
      '--info-text': 'var(--info-foreground)',
      '--info-border': 'var(--info)',
    }"
    :toast-options="{
      class: 'items-start!',
      classes: {
        icon: 'mt-0.5',
        toast: 'group toast group-[.toaster]:shadow-lg',
        actionButton:
          'bg-transparent! text-current! border! border-solid! border-current! font-semibold! hover:bg-current/10! focus-visible:outline-2! focus-visible:outline-offset-2! focus-visible:outline-current! focus-visible:shadow-none!',
        cancelButton: 'bg-transparent! text-current! hover:bg-current/10!',
      },
    }"
  />
</template>
