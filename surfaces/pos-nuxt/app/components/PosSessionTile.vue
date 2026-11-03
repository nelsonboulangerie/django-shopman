<script setup lang="ts">
// Um card do Caixa (pages/session). O card É a escolha (dono, 25/09/2026): nome do
// ato, ícone e uma linha dizendo o que vai acontecer; o formulário ou a lista só
// aparece depois do toque.
//
// É o card da suíte (`NuxtPageCard`, o mesmo contrato dos Ajustes do Gestor), e não
// uma pele própria: o PDV tinha um quadrado desenhado à mão, com o ícone num ladrilho,
// que destoava dos outros apps. Aqui ele é um botão (`as="button"`): o card abre um
// diálogo, e só um botão de verdade recebe o teclado e o `disabled`.
//
// A pele sai do `tone` (ver `SessionTile` em presentation/cash):
// - `primary`: o próximo gesto óbvio, com o realce dourado da suíte;
// - `attention`: pendência que pede gente, com o realce de atenção;
// - `destructive`: encerra algo, vermelho SÓ no ícone;
// - `default`: o resto.
import type { SessionTile } from "~/presentation/cash";

const props = defineProps<{ tile: SessionTile }>();
const emit = defineEmits<{ select: [tile: SessionTile] }>();

const icon = computed(() => props.tile.icon.replace(/^lucide:/, "i-lucide-"));
const highlighted = computed(() => props.tile.tone === "primary" || props.tile.tone === "attention");
const iconTone = computed(() => {
  if (props.tile.tone === "destructive") return "text-error";
  if (props.tile.tone === "attention") return "text-warning";
  return "text-primary";
});
const badgeColor = computed(() => {
  if (props.tile.tone === "attention") return "warning" as const;
  if (props.tile.tone === "primary") return "primary" as const;
  return "neutral" as const;
});

function select() {
  if (!props.tile.disabled) emit("select", props.tile);
}
</script>

<template>
  <NuxtPageCard
    as="button"
    type="button"
    :icon="icon"
    :title="tile.label"
    :description="tile.description"
    :variant="tile.tone === 'attention' ? 'soft' : 'outline'"
    :highlight="highlighted"
    :highlight-color="tile.tone === 'attention' ? 'warning' : 'primary'"
    :disabled="tile.disabled"
    :ui="{
      root: 'h-full w-full cursor-pointer text-left disabled:cursor-not-allowed disabled:opacity-60',
      container: 'p-4 sm:p-4',
      leadingIcon: `size-6 ${iconTone}`,
      title: 'text-sm font-semibold',
      description: 'text-sm',
    }"
    :data-session-tile="tile.key"
    :data-tone="tile.tone"
    @click="select"
  >
    <NuxtBadge
      v-if="tile.badge"
      :label="tile.badge"
      :color="badgeColor"
      variant="solid"
      class="absolute right-3 top-3 tabular-nums"
      data-session-tile-badge
    />
  </NuxtPageCard>
</template>
