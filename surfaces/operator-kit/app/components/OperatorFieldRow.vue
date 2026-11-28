<script setup lang="ts">
// Uma linha de campos relacionados se organiza pelo significado, não pela tela que a usa.
// `priority` reserva mais espaço ao valor ou ao contexto; um detalhe condicional sempre
// abre uma linha própria. Em telas muito estreitas, tudo empilha sem o consumidor medir pixels.
withDefaults(
  defineProps<{
    priority?: "balanced" | "value" | "context";
  }>(),
  { priority: "balanced" },
);
</script>

<template>
  <div
    class="grid min-w-0 grid-cols-1 gap-2"
    :class="{
      'min-[360px]:grid-cols-2': priority === 'balanced',
      'min-[360px]:grid-cols-[minmax(0,1fr)_minmax(6rem,0.55fr)]': priority === 'value',
      'min-[360px]:grid-cols-[minmax(7rem,2fr)_minmax(0,3fr)]': priority === 'context',
    }"
    data-operator-field-row
    :data-priority="priority"
  >
    <div class="min-w-0" data-operator-field-value>
      <slot name="value" />
    </div>
    <div class="min-w-0" data-operator-field-context>
      <slot name="context" />
    </div>
    <div v-if="$slots.detail" class="min-w-0 min-[360px]:col-span-2" data-operator-field-detail>
      <slot name="detail" />
    </div>
  </div>
</template>
