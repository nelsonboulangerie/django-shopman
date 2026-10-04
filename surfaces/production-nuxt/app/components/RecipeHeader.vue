<script setup lang="ts">
// Cabeçalho das telas de receitas na camada visual da suíte (V4-PROD): o mesmo
// `OperatorPageHeader` de uma linha das outras telas da Produção, com a linha fina
// "Receitas" acima do título, o voltar (`#lead`), a busca e os controles da tela. SEM o
// progresso do dia nem as teclas do ciclo: o inventário de receitas não é etapa do lote,
// é conhecimento da casa. Receitas mora no pé do rail (e no ⋯ do celular).
const props = defineProps<{
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

const eyebrow = computed(() =>
  props.subtitle ? `Receitas · ${props.subtitle}` : "Receitas",
);
</script>

<template>
  <OperatorPageHeader :title="title" :eyebrow="eyebrow">
    <template v-if="back" #lead>
      <NuxtLink
        :to="back"
        class="grid size-control shrink-0 place-items-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground"
        aria-label="Voltar"
        title="Voltar"
      >
        <Icon name="lucide:arrow-left" class="size-5" />
      </NuxtLink>
    </template>
    <template v-if="searchable" #search>
      <OperatorSuiteSearch
        v-model="query"
        class="suite:md:w-[18rem]!"
        screen-label="filtrando as receitas"
        placeholder="Buscar receita"
        :aria-label="searchLabel || 'Buscar por nome, ref ou SKU'"
      />
    </template>
    <template #actions>
      <slot name="actions" />
      <UiIconButton
        v-if="!hideRefresh"
        icon="lucide:refresh-cw"
        label="Atualizar"
        :spinning="pending"
        @click="emit('refresh')"
      />
    </template>
  </OperatorPageHeader>
</template>
