<script setup lang="ts">
// Um quadro de leitura: título que diz o que se vê, a legenda curta de como ler, e o
// conteúdo. É o NuxtCard canônico (cabeçalho e corpo do tema do kit), com o título em
// `op-title` e a legenda em `op-micro`. `#aside` põe um controle na linha do título
// (o ⋯ de exportar). Altura do próprio conteúdo.
defineProps<{ title: string; caption?: string }>();
</script>

<template>
  <NuxtCard as="section" data-bi-section>
    <template #header>
      <div class="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div class="min-w-0">
          <h2 class="op-title text-foreground">{{ title }}</h2>
          <p v-if="caption || $slots.caption" class="op-micro text-muted-foreground">
            <slot name="caption">{{ caption }}</slot>
          </p>
        </div>
        <slot name="aside" />
      </div>
    </template>
    <slot />
  </NuxtCard>
</template>
