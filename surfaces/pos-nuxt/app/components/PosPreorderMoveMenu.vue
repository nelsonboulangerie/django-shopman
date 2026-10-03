<script setup lang="ts">
// "Mudar de dia", no card da encomenda: o mesmo gesto de arrastar o card para
// outro dia da semana, por teclado e por toque (arrastar não existe para quem
// não usa mouse, e no tablet o arrastar nativo não é confiável). Os dias da tela
// para onde ela pode ir, um toque cada; e "Outra data ou horário…", que abre o
// Reagendar completo (qualquer dia, a janela). Quem pergunta, avisa e grava é a
// página (`usePosPreorderMove`); aqui só se escolhe.
import type { MoveTarget } from "~/presentation/preorders";

const props = defineProps<{
  customerName: string;
  targets: readonly MoveTarget[];
  busy?: boolean;
}>();

const emit = defineEmits<{ move: [date: string]; other: [] }>();

const open = ref(false);
const label = computed(() => (props.customerName.trim()
  ? `Mudar de dia a encomenda de ${props.customerName.trim()}`
  : "Mudar de dia a encomenda"));

function pick(date: string) {
  open.value = false;
  emit("move", date);
}

function other() {
  open.value = false;
  emit("other");
}
</script>

<template>
  <UiPopover v-model:open="open">
    <UiPopoverTrigger as-child>
      <UiButton
        variant="ghost"
        size="icon"
        class="h-full min-h-control w-10 rounded-none rounded-r-md text-muted-foreground"
        :aria-label="label"
        title="Mudar de dia"
        :disabled="busy"
        data-preorder-move-menu
      >
        <Icon name="lucide:calendar-clock" class="size-4" aria-hidden="true" />
      </UiButton>
    </UiPopoverTrigger>
    <UiPopoverContent align="end" class="w-56 p-1">
      <template v-if="targets.length">
        <p class="px-2 py-1.5 text-xs font-medium text-muted-foreground">Mudar para</p>
        <div role="group" aria-label="Mudar para">
          <button
            v-for="target in targets"
            :key="target.date"
            type="button"
            class="flex min-h-control w-full items-center gap-2 rounded-md px-2 text-left text-sm transition hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            :data-preorder-move-to="target.date"
            @click="pick(target.date)"
          >
            <Icon name="lucide:calendar" class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            {{ target.label }}
          </button>
        </div>
        <UiSeparator class="my-1" />
      </template>
      <button
        type="button"
        class="flex min-h-control w-full items-center gap-2 rounded-md px-2 text-left text-sm transition hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        data-preorder-move-other
        @click="other"
      >
        <Icon name="lucide:calendar-cog" class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        Outra data ou horário…
      </button>
    </UiPopoverContent>
  </UiPopover>
</template>
