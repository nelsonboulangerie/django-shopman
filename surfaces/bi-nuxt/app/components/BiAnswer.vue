<script setup lang="ts">
// "A resposta" (prévia `bi-sobra4.html`, pino 5): a pergunta do título respondida em
// uma frase, antes de qualquer número ou gráfico. A frase sai da presentation, montada
// com os dados da leitura; nunca é texto fixo.
defineProps<{ text: string }>();
</script>

<template>
  <div class="rounded-lg border border-border bg-card px-4 py-3" data-bi-answer>
    <p class="op-eyebrow text-muted-foreground">A resposta</p>
    <p class="mt-0.5 op-title text-foreground">{{ text }}</p>
  </div>
</template>
