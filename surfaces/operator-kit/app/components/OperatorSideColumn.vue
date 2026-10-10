<script setup lang="ts">
// COLUNA LATERAL DIREITA DE LARGURA AJUSTÁVEL (primeiro consumidor: a comanda do
// PDV, dono 10/10). A estrutura é a canônica do Nuxt UI: um `DashboardGroup` próprio
// (a largura não se mistura com a do rail) com a `DashboardSidebar` do lado direito,
// `resizable`, em rem, gravada em cookie (`<storageKey>-sidebar-<columnId>`); dois
// cliques na alça voltam ao padrão. A alça é a da primitiva, com teclado e toque.
//
// `docked = false` (abaixo do desktop, quando a coluna vira folha ou some): o
// conteúdo da coluna sai num `<aside>` simples, no fluxo, sem alça. O app decide.
//
// O tom do rail (`app.config`, `dashboardSidebar`) é só da barra da ESQUERDA: esta
// coluna fala com os tokens da tela.
const props = withDefaults(
  defineProps<{
    /** Chave do grupo (cookie). Uma por tela. */
    storageKey: string;
    /** Id da coluna dentro do grupo. */
    columnId: string;
    /** Na mesa: coluna inteira à direita, ajustável. Fora dela: `<aside>` no fluxo. */
    docked?: boolean;
    /** Larguras em rem: o mínimo é o menor em que o conteúdo cabe sem cortar. */
    minSize: number;
    maxSize: number;
    defaultSize: number;
    /** Atributos da coluna (os `data-*` que as travas e os testes leem). */
    columnAttrs?: Record<string, string | boolean>;
  }>(),
  { docked: true, columnAttrs: () => ({}) },
);

const COLUMN_UI = {
  root: "h-full min-h-0 border-s border-default bg-card",
  body: "gap-0 overflow-hidden p-0",
  // A coluna pinta por cima da borda; a alça fica acima dela para ser alcançável.
  handle: "z-40",
};
</script>

<template>
  <NuxtDashboardGroup
    :storage-key="props.storageKey"
    unit="rem"
    class="relative inset-auto flex min-h-0 flex-1 max-lg:flex-col"
    data-operator-side-column-layout
  >
    <slot />
    <template v-if="$slots.column">
      <NuxtDashboardSidebar
        v-if="props.docked"
        :id="props.columnId"
        side="right"
        resizable
        :min-size="props.minSize"
        :max-size="props.maxSize"
        :default-size="props.defaultSize"
        :toggle="false"
        :open="false"
        :ui="COLUMN_UI"
        data-operator-side-column
        v-bind="props.columnAttrs"
      >
        <slot name="column" />
      </NuxtDashboardSidebar>
      <aside v-else class="relative z-30 flex shrink-0 flex-col" data-operator-side-column v-bind="props.columnAttrs">
        <slot name="column" />
      </aside>
    </template>
  </NuxtDashboardGroup>
</template>
