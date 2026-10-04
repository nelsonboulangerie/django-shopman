<script setup lang="ts">
// O ⋯ do cabeçalho (prévia `depois-marketing-campanhas`, pino 4): o que não é o gesto
// principal da tela mora aqui, a um toque. Itens são links (para outra tela) ou ações
// (Atualizar, com a tecla ao lado). Atalhos de teclado do app e o painel deles são do
// kit; aqui só a tecla da própria ação.
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";

export interface MarketingMenuItem {
  key: string;
  label: string;
  icon: string;
  /** Rota de destino; sem ela, o item emite `select`. */
  to?: string;
  /** A tecla que faz o mesmo ("R"). */
  shortcut?: string;
}

defineProps<{ heading: string; items: MarketingMenuItem[] }>();
const emit = defineEmits<{ select: [key: string] }>();

const open = ref(false);
const ITEM =
  "flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent focus-visible:bg-accent focus-visible:outline-none";

function choose(key: string) {
  open.value = false;
  emit("select", key);
}
</script>

<template>
  <PopoverRoot v-model:open="open">
    <PopoverTrigger as-child>
      <UiIconButton icon="lucide:ellipsis" :label="`Mais: ${heading}`" :active="open" data-marketing-page-menu />
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent
        side="bottom"
        align="end"
        :side-offset="6"
        :collision-padding="8"
        class="z-50 w-64 rounded-lg border bg-popover p-1.5 text-popover-foreground shadow-lg outline-hidden"
        data-marketing-page-menu-panel
      >
        <p class="px-2.5 pt-1 pb-1.5 op-eyebrow text-muted-foreground">{{ heading }}</p>
        <div role="menu" class="flex flex-col">
          <template v-for="item in items" :key="item.key">
            <NuxtLink v-if="item.to" :to="item.to" role="menuitem" :class="ITEM" @click="open = false">
              <Icon :name="item.icon" class="size-4 text-muted-foreground" aria-hidden="true" />
              <span class="flex-1">{{ item.label }}</span>
              <kbd v-if="item.shortcut" class="op-micro text-muted-foreground">{{ item.shortcut }}</kbd>
            </NuxtLink>
            <button v-else type="button" role="menuitem" :class="ITEM" @click="choose(item.key)">
              <Icon :name="item.icon" class="size-4 text-muted-foreground" aria-hidden="true" />
              <span class="flex-1">{{ item.label }}</span>
              <kbd v-if="item.shortcut" class="op-micro text-muted-foreground">{{ item.shortcut }}</kbd>
            </button>
          </template>
        </div>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
