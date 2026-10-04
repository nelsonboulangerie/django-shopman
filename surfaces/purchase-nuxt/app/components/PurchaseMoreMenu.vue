<script setup lang="ts">
// O ⋯ das telas do Compras (Base: Atualizar; Receber: Trocar NF, Sem NF, Ressalva
// geral, Registrar devolução). Popover do reka-ui, como o resto da layer em apps
// sem `UiPopover`. `vertical` desenha o ⋮ da barra do celular.
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";

export interface MoreMenuItem {
  key: string;
  label: string;
  icon: string;
  danger?: boolean;
  disabled?: boolean;
  /** Linha fina antes do item (separa grupos). */
  divider?: boolean;
}

const props = withDefaults(
  defineProps<{ items: MoreMenuItem[]; label?: string; vertical?: boolean }>(),
  { label: "Mais", vertical: false },
);
const emit = defineEmits<{ select: [key: string] }>();
const open = ref(false);

function choose(key: string) {
  open.value = false;
  emit("select", key);
}
</script>

<template>
  <PopoverRoot v-model:open="open">
    <PopoverTrigger as-child>
      <button
        type="button"
        class="grid shrink-0 place-items-center rounded-md text-foreground transition hover:bg-accent"
        :class="vertical ? 'size-12' : 'size-control border border-border bg-card'"
        :aria-label="props.label"
        :title="props.label"
        data-purchase-more
      >
        <Icon :name="vertical ? 'lucide:ellipsis-vertical' : 'lucide:ellipsis'" class="size-5" />
      </button>
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent
        align="end"
        :side-offset="6"
        :collision-padding="8"
        class="z-50 w-64 rounded-md border bg-popover p-1.5 text-popover-foreground shadow-md outline-hidden"
      >
        <div role="menu" data-purchase-more-panel>
          <template v-for="item in items" :key="item.key">
            <div v-if="item.divider" class="my-1.5 border-t border-border" />
            <button
              type="button"
              role="menuitem"
              class="flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent disabled:opacity-50"
              :class="item.danger ? 'text-destructive hover:bg-destructive/10' : ''"
              :disabled="item.disabled"
              :data-purchase-more-item="item.key"
              @click="choose(item.key)"
            >
              <Icon :name="item.icon" class="size-4" :class="item.danger ? '' : 'text-muted-foreground'" />
              {{ item.label }}
            </button>
          </template>
        </div>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
