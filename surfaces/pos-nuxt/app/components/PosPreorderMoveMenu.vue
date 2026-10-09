<script setup lang="ts">
// "Mudar de dia", no card da encomenda: o mesmo gesto de arrastar o card para
// outro dia da semana, por teclado e por toque (arrastar não existe para quem
// não usa mouse, e no tablet o arrastar nativo não é confiável). É o ⋯ único do
// kit (`OperatorMoreMenu`) no cartão: os dias da tela para onde ela pode ir, um
// toque cada; e "Outra data ou horário…", que abre o Reagendar completo (qualquer
// dia, a janela). Quem pergunta, avisa e grava é a página (`usePosPreorderMove`);
// aqui só se escolhe.
import type { OperatorMoreMenuItem } from "../../../operator-kit/app/presentation/moreMenu";
import type { MoveTarget } from "~/presentation/preorders";

const props = defineProps<{
  customerName: string;
  targets: readonly MoveTarget[];
  busy?: boolean;
}>();

const emit = defineEmits<{ move: [date: string]; other: [] }>();

const label = computed(() => (props.customerName.trim()
  ? `Mudar de dia a encomenda de ${props.customerName.trim()}`
  : "Mudar de dia a encomenda"));

const items = computed<OperatorMoreMenuItem[][]>(() => {
  const other: OperatorMoreMenuItem = {
    label: "Outra data ou horário…",
    icon: "i-lucide-calendar-cog",
    "data-preorder-move-other": "",
    onSelect: () => emit("other"),
  };
  if (!props.targets.length) return [[other]];
  return [
    [
      { type: "label", label: "Mudar para" },
      ...props.targets.map((target) => ({
        label: target.label,
        icon: "i-lucide-calendar",
        "data-preorder-move-to": target.date,
        onSelect: () => emit("move", target.date),
      })),
    ],
    [other],
  ];
});
</script>

<template>
  <OperatorMoreMenu
    :items="items"
    :label="label"
    :disabled="busy"
    class="h-full rounded-none rounded-r-md"
    data-preorder-move-menu
  />
</template>
