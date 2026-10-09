<script setup lang="ts">
// O workspace modal dos fluxos densos (contrato do Marketing: criar e editar campanha,
// modelo, oferta e cupom, e o detalhe de uma plataforma). Um `NuxtModal` só, com a
// medida escrita UMA vez aqui, pela `class` do modal (que vai ao conteúdo e se funde
// com o tema; nenhum `:ui`):
//
// - celular: ocupa a tela inteira (`h-dvh`, `w-screen`, sem raio);
// - do `sm` para cima: usa a largura da mesa até 1280 px e a altura até 900 px;
// - o corpo do modal rola sozinho (o tema do `NuxtModal` põe `overflow-y-auto` no `body` quando `scrollable` fica desligado), o título e o fechar
//   ficam;
// - fechar devolve o foco a quem abriu (o `FocusScope` do Reka guarda o elemento que
//   tinha o foco quando o diálogo montou e o devolve ao desmontar). A tela que troca a
//   lista ao fechar (Plataformas, que volta à própria rota) devolve o foco à linha.
//
// Interface estável (Campanhas, Modelos, Ofertas e cupons, Plataformas): `open`,
// `title`, `description`, `update:open` e o slot padrão.
defineProps<{
  open: boolean;
  title: string;
  description: string;
}>();

const emit = defineEmits<{
  "update:open": [value: boolean];
}>();

// Celular: a tela inteira. Do `sm` para cima: a largura da mesa até 1280 px.
const WORKSPACE_CLASS =
  "h-dvh max-h-dvh w-screen max-w-none rounded-none ring-0 sm:h-[min(900px,calc(100dvh-3rem))] sm:max-h-[calc(100dvh-3rem)] sm:w-[min(1280px,calc(100vw-3rem))] sm:max-w-[min(1280px,calc(100vw-3rem))] sm:rounded-lg sm:ring";
</script>

<template>
  <NuxtModal
    :open="open"
    :title="title"
    :description="description"
    :class="WORKSPACE_CLASS"
    data-marketing-workspace
    @update:open="emit('update:open', $event)"
  >
    <template #body>
      <div class="mx-auto w-full max-w-6xl">
        <slot />
      </div>
    </template>
  </NuxtModal>
</template>
