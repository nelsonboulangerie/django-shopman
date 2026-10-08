<script setup lang="ts">
// Lista vertical de ações dentro de gaveta ou diálogo: o "Mais" da Fila no celular, o
// ⋯ do detalhe e os cadastros achados na unificação. O ⋯ que abre ancorado no botão é
// NuxtDropdownMenu; aqui é o mesmo formato de itens (grupos, rótulo, separador,
// ícone, descrição, atalho, `data-*`), em NuxtButton, como o menu do operador do kit.
// O NavigationMenu fazia esse papel e é peça de navegação, reservada ao kit pelo
// ledger (`scripts/check_operator_component_ledger.py`). Candidata a subir ao kit.
import { computed } from "vue";

export type ActionListItem = {
  label?: string;
  description?: string;
  icon?: string;
  type?: "label" | "separator";
  /** Item que quem chama desenha fora da lista (ex.: a leitura da fila). */
  slot?: string;
  color?: "neutral" | "primary" | "error" | "warning" | "success" | "info";
  disabled?: boolean;
  loading?: boolean;
  title?: string;
  to?: string;
  kbds?: string[];
  onSelect?: () => void;
  [key: `data-${string}`]: string | undefined;
};

const props = defineProps<{
  items: ActionListItem[] | ActionListItem[][];
  ariaLabel?: string;
}>();

const groups = computed(() =>
  (Array.isArray(props.items[0])
    ? (props.items as ActionListItem[][])
    : [props.items as ActionListItem[]]
  )
    .map((group) => group.filter((item) => !item.slot))
    .filter((group) => group.length),
);

function dataAttrs(item: ActionListItem) {
  return Object.fromEntries(
    Object.entries(item).filter(([key]) => key.startsWith("data-")),
  );
}
</script>

<template>
  <div
    class="flex flex-col"
    role="group"
    :aria-label="ariaLabel"
    data-action-list
  >
    <template v-for="(group, groupIndex) in groups" :key="groupIndex">
      <NuxtSeparator v-if="groupIndex > 0" class="my-1" />
      <template v-for="(item, index) in group" :key="`${groupIndex}-${index}`">
        <NuxtSeparator v-if="item.type === 'separator'" class="my-1" />
        <p
          v-else-if="item.type === 'label'"
          class="px-2.5 pt-2 pb-1 op-eyebrow text-muted-foreground"
        >
          {{ item.label }}
        </p>
        <NuxtButton
          v-else
          v-bind="dataAttrs(item)"
          block
          class="justify-start"
          :color="item.color ?? 'neutral'"
          variant="ghost"
          :icon="item.icon"
          :loading="item.loading"
          :disabled="item.disabled"
          :title="item.title"
          :to="item.to"
          @click="item.onSelect?.()"
        >
          <span class="flex min-w-0 flex-1 flex-col items-start text-start">
            <span class="truncate">{{ item.label }}</span>
            <span
              v-if="item.description"
              class="op-micro text-muted-foreground"
              >{{ item.description }}</span
            >
          </span>
          <template v-if="item.kbds?.length" #trailing>
            <NuxtKbd
              v-for="kbd in item.kbds"
              :key="kbd"
              :value="kbd"
              variant="soft"
            />
          </template>
        </NuxtButton>
      </template>
    </template>
  </div>
</template>
