<script setup lang="ts">
// O polegar do celular: o gesto principal da tela num botão largo, preso na base da área
// que rola, logo acima da barra de baixo (F7, dono 09/10/2026; prévia v4
// `cozinha-celular` (a): "Entregar U13 a Ana"). É a porta por botão do que a linha
// também faz deslizando (`OperatorSwipeRow`), e por isso nunca some quando o deslize
// existe: quem não desliza, quem usa leitor de tela e quem usa teclado chegam ao mesmo
// ato por aqui.
//
// Regras da peça:
//   - Só no celular (`md:hidden`): do tablet para cima o botão do próprio cartão já
//     está ao alcance.
//   - Um por tela, com o verbo e o alvo escritos ("Entregar U13 a Ana", "Despachar
//     M09"), nunca um "Confirmar" solto: o cartão a que ele se refere pode estar fora
//     da vista.
//   - Ocupa a base como chrome (`data-focus-obstruction`): o próximo foco e o "Tem mais
//     abaixo" descontam a altura dele.
//   - Botão `xl` `solid` `primary`: toque crítico, do conjunto mínimo da suíte.
withDefaults(
  defineProps<{
    label: string;
    /** Ícone no formato `i-lucide-nome`. */
    icon?: string;
    loading?: boolean;
    disabled?: boolean;
  }>(),
  { icon: "i-lucide-hand-platter", loading: false, disabled: false },
);
const emit = defineEmits<{ press: [] }>();
</script>

<template>
  <div
    class="sticky bottom-0 z-20 -mx-px mt-auto bg-gradient-to-t from-background from-70% to-transparent pt-6 pb-1 md:hidden"
    data-focus-obstruction
    data-thumb-action
  >
    <NuxtButton
      size="xl"
      block
      :icon="icon"
      :label="label"
      :loading="loading"
      :disabled="disabled"
      @click="emit('press')"
    />
  </div>
</template>
