<script setup lang="ts">
// A seção de um cadastro: um bloco nomeado de campos, com a chave do próximo
// foco. O `OperatorFormShell` leva a página até a seção quando ela é a chave do
// momento; o controle que deve receber o foco de teclado se marca com
// `data-focus-control`, dentro do slot.
//
// Sem cartão próprio: quem chama decide o chrome (um `NuxtCard` em volta, ou os
// campos direto na superfície do painel), e a seção só dá o nome e a linha.
withDefaults(
  defineProps<{
    /** A chave do bloco para o próximo foco ("identity", "price"). */
    sectionKey: string;
    title?: string;
    description?: string;
  }>(),
  { title: "", description: "" },
);
</script>

<template>
  <section
    :data-focus-target="sectionKey"
    class="flex scroll-mt-20 flex-col gap-3 outline-none"
    tabindex="-1"
  >
    <div v-if="title || description" class="flex flex-col gap-0.5">
      <h2 v-if="title" class="op-title">{{ title }}</h2>
      <p v-if="description" class="text-xs text-muted-foreground">{{ description }}</p>
    </div>
    <slot />
  </section>
</template>
