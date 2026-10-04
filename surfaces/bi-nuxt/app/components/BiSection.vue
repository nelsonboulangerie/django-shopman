<script setup lang="ts">
// Um quadro de leitura: título que diz o que se vê, a legenda curta de como ler, e o
// conteúdo. Mesmo cartão das prévias (`rounded-lg border bg-card`), com o título em
// `op-title` e a legenda em `op-micro`. `#aside` põe um controle na linha do título.
defineProps<{ title: string; caption?: string }>();
</script>

<template>
  <section class="rounded-lg border border-border bg-card px-4 py-3">
    <div class="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
      <div class="min-w-0">
        <h2 class="op-title text-foreground">{{ title }}</h2>
        <p v-if="caption || $slots.caption" class="op-micro text-muted-foreground">
          <slot name="caption">{{ caption }}</slot>
        </p>
      </div>
      <slot name="aside" />
    </div>
    <div class="mt-3">
      <slot />
    </div>
  </section>
</template>
