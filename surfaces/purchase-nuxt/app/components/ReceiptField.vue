<script setup lang="ts">
/**
 * Um campo da linha de recebimento, com o destaque de quando ele pede decisão.
 *
 * O padrão é um só para TODO campo que espera algo do operador — insumo,
 * conversão, validade, lote. A proposta ou a cobrança fica dentro do card, junto
 * do campo de que ela fala, e o card some quando não há mais o que decidir. A
 * alternativa (caixas soltas ao lado dos campos) obrigava o operador a ligar uma
 * coisa à outra de cabeça, com o entregador esperando.
 */
withDefaults(
  defineProps<{
    /** Precisa de decisão agora. Sem isto, o campo é comum. */
    attention?: boolean;
    /** O gesto pedido, em uma frase: "Informe a validade". */
    title?: string;
    /** Erro em vez de pendência — a nota discorda de algo já preenchido. */
    wrong?: boolean;
    icon?: string;
  }>(),
  { attention: false, title: "", wrong: false, icon: "lucide:circle-alert" },
);
</script>

<template>
  <div
    :class="
      attention ?
        wrong ? 'rounded-md border border-destructive/40 bg-destructive/10 p-3'
        : 'rounded-md border border-warning/40 bg-warning/10 p-3'
      : ''
    "
  >
    <p
      v-if="attention && title"
      class="mb-2 flex items-center gap-1.5 text-xs font-semibold"
      :class="wrong ? 'text-destructive' : 'text-warning'"
    >
      <Icon :name="icon" class="size-3.5 shrink-0" />
      {{ title }}
    </p>
    <slot />
  </div>
</template>
