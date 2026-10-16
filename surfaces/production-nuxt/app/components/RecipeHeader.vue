<script setup lang="ts">
// Cabeçalho das telas de receitas: o mesmo `OperatorPageHeader` do kit das outras
// telas da Produção, com o selo "Receitas" ao lado do título, o voltar (`#lead`), a
// busca e a ação primária da tela. Atualizar mora no ⋯ "Mais ações" (dados). SEM o
// progresso do dia: o inventário de receitas não é etapa do lote, é conhecimento da
// casa. Receitas mora em Ajustes. O `#status` repassa o "onde estou" da tela (o
// anterior e próxima da receita, `OperatorRecordNav`) ao mesmo slot do cabeçalho.
import type { OperatorHeaderAction } from "../../../operator-kit/app/presentation/pageHeader";

const props = defineProps<{
  title: string;
  /** Linha pequena ao lado de "Receitas" (kind, SKU, versão) — opcional. */
  subtitle?: string;
  /** Rota de volta (seta à esquerda do título). */
  back?: string;
  /** Mostra a busca ligada a `v-model:query`. */
  searchable?: boolean;
  /** Placeholder e rótulo acessível da busca. */
  searchLabel?: string;
  pending?: boolean;
  /** Esconde Atualizar (telas sem leitura própria, como o editor). */
  hideRefresh?: boolean;
  /** A ação primária da tela: botão na mesa, ícone fixo (ou topo do ⋯) no celular. */
  primary?: OperatorHeaderAction;
}>();
const emit = defineEmits<{ refresh: [] }>();
const query = defineModel<string>("query", { default: "" });

const eyebrow = computed(() =>
  props.subtitle ? `Receitas · ${props.subtitle}` : "Receitas",
);
const refreshAction = computed<OperatorHeaderAction[]>(() =>
  props.hideRefresh
    ? []
    : [{ label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => emit("refresh") }],
);
// Mesa: a primária é botão no `#actions` e o ⋯ só leva Atualizar. Celular: a primária
// disputa a vaga de ícone (priority 1) e Atualizar vai para o ⋯.
const deskActions = computed(() => (refreshAction.value.length ? refreshAction.value : undefined));
const phoneActions = computed(() => {
  const list = [...(props.primary ? [{ ...props.primary, priority: 1 }] : []), ...refreshAction.value];
  return list.length ? list : undefined;
});
</script>

<template>
  <OperatorPageHeader
    :title="title"
    :eyebrow="eyebrow"
    :actions="deskActions"
    :phone-actions="phoneActions"
    actions-label="Mais ações da tela"
  >
    <template v-if="back" #lead>
      <NuxtButton
        :to="back"
        icon="i-lucide-arrow-left"
        color="neutral"
        variant="ghost"
        square
        aria-label="Voltar"
        title="Voltar"
      />
    </template>
    <template v-if="$slots.status" #status>
      <slot name="status" />
    </template>
    <template v-if="searchable" #search>
      <OperatorSuiteSearch
        v-model="query"
        screen-label="filtrando as receitas"
        placeholder="Buscar receita"
        :aria-label="searchLabel || 'Buscar por nome, ref ou SKU'"
      />
    </template>
    <template v-if="primary || $slots.actions" #actions>
      <slot name="actions" />
      <NuxtButton
        v-if="primary"
        :to="primary.to"
        :icon="primary.icon"
        :label="primary.label"
        :disabled="primary.disabled"
        @click="primary.onSelect?.($event)"
      />
    </template>
  </OperatorPageHeader>
</template>
