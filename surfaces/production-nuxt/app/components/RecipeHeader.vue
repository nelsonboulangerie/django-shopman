<script setup lang="ts">
// Cabeçalho das telas de receitas — irmão do ProductionHeader (mesmo lugar, mesmo
// desenho: RailToggle + eyebrow + título + busca + atualizar), SEM as abas do fluxo
// do dia: o inventário de receitas não é etapa da fornada, é conhecimento da casa.
// O que é comum (Central, operador/travar, tema) mora no OperatorRail à esquerda.
defineProps<{
  title: string;
  /** Linha pequena sob o título (kind, SKU, versão) — opcional. */
  subtitle?: string;
  /** Rota de volta (seta à esquerda do título). */
  back?: string;
  /** Mostra a busca ligada a `v-model:query`. */
  searchable?: boolean;
  /** Placeholder e rótulo acessível da busca. */
  searchLabel?: string;
  pending?: boolean;
  /** Esconde o botão Atualizar (telas sem leitura própria, como o editor). */
  hideRefresh?: boolean;
}>();
const emit = defineEmits<{ refresh: [] }>();
const query = defineModel<string>("query", { default: "" });
</script>

<template>
  <header class="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b bg-card px-4 py-2.5">
    <RailToggle />
    <NuxtLink
      v-if="back"
      :to="back"
      class="grid size-9 shrink-0 place-items-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground"
      aria-label="Voltar"
      title="Voltar"
    >
      <Icon name="lucide:arrow-left" class="size-5" />
    </NuxtLink>
    <div class="mr-2 min-w-0">
      <p class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Receitas</p>
      <h1 class="truncate text-lg font-bold leading-tight">{{ title }}</h1>
      <p v-if="subtitle" class="truncate text-xs text-muted-foreground">{{ subtitle }}</p>
    </div>

    <div class="ml-auto flex items-center gap-1.5">
      <slot name="actions" />
      <div v-if="searchable" class="relative">
        <Icon
          name="lucide:search"
          class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <input
          v-model="query"
          type="search"
          inputmode="search"
          placeholder="Buscar…"
          class="h-9 w-32 rounded-md border bg-background pl-8 pr-7 text-sm outline-none transition focus:w-44 focus:ring-1 focus:ring-ring sm:w-40"
          :aria-label="searchLabel || 'Buscar por nome, ref ou SKU'"
        />
        <button
          v-if="query"
          type="button"
          class="absolute right-1 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded text-muted-foreground transition hover:text-foreground"
          aria-label="Limpar busca"
          @click="query = ''"
        >
          <Icon name="lucide:x" class="size-3.5" />
        </button>
      </div>
      <AlertsBell />
      <button
        v-if="!hideRefresh"
        type="button"
        class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground"
        aria-label="Atualizar"
        title="Atualizar"
        @click="emit('refresh')"
      >
        <Icon name="lucide:refresh-cw" class="size-4" :class="pending ? 'animate-spin' : ''" />
      </button>
    </div>
  </header>
</template>
