<script setup lang="ts">
// As sugestões de uma promessa em risco (dono, 19/11/2026): o que a casa pode oferecer
// no lugar do item que falta, uma por linha, com marcador, sob "Sugestões:". Os nomes e
// o quanto há vêm do servidor (`promise.items[].alternatives`, o mesmo mecanismo de
// substitutos da loja); aqui só se desenha a lista. Sem opção, nada é desenhado: quando
// o servidor procurou e não achou, quem diz é a frase do próximo passo.
withDefaults(
  defineProps<{
    options: readonly string[];
    /** "Sugestões:", ou "Sugestões para Baguete:" quando a linha fala de mais de um item. */
    heading?: string;
  }>(),
  { heading: "Sugestões:" },
);
</script>

<template>
  <div v-if="options.length" class="flex flex-col gap-0.5" data-promise-suggestions>
    <p class="font-medium">{{ heading }}</p>
    <ul class="list-disc ps-5">
      <li v-for="option in options" :key="option" data-promise-suggestion>
        {{ option }}
      </li>
    </ul>
  </div>
</template>
