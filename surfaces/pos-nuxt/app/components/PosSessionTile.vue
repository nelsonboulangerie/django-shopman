<script setup lang="ts">
// Um card da antesala (pages/session). O card É a escolha: nome do ato, ícone
// e uma linha dizendo o que vai acontecer — o formulário ou a lista só aparece
// depois do toque. A pele sai do `tone` (ver `SessionTile` em
// presentation/cash): `primary` é o gesto óbvio da tela, card cheio;
// `attention` é pendência que pede gente; `destructive` pinta só o ícone.
import type { SessionTile } from "~/presentation/cash";

const props = defineProps<{ tile: SessionTile }>();
defineEmits<{ select: [tile: SessionTile] }>();

const cardClass = computed(() => {
  if (props.tile.tone === "primary") {
    return "border-primary bg-primary text-primary-foreground hover:bg-primary/90";
  }
  if (props.tile.tone === "attention") {
    return "border-warning/50 bg-warning/5 hover:border-warning hover:bg-warning/10";
  }
  return "border-border bg-card hover:border-primary/40 hover:bg-accent";
});

const iconClass = computed(() => {
  if (props.tile.tone === "primary") return "bg-primary-foreground/15 text-primary-foreground";
  if (props.tile.tone === "attention") return "bg-warning/15 text-warning";
  if (props.tile.tone === "destructive") return "bg-destructive/10 text-destructive";
  return "bg-primary/10 text-primary";
});

const descriptionClass = computed(() =>
  props.tile.tone === "primary" ? "text-primary-foreground/80" : "text-muted-foreground",
);

const badgeClass = computed(() => {
  if (props.tile.tone === "primary") return "bg-primary-foreground text-primary";
  if (props.tile.tone === "attention") return "bg-warning text-warning-foreground";
  return "border border-border bg-muted text-muted-foreground";
});
</script>

<template>
  <button
    type="button"
    class="relative flex min-h-28 w-full flex-col gap-2 rounded-md border p-4 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
    :class="cardClass"
    :disabled="tile.disabled"
    :data-session-tile="tile.key"
    :data-tone="tile.tone"
    @click="$emit('select', tile)"
  >
    <span class="flex items-start justify-between gap-2">
      <span class="grid size-11 place-items-center rounded-md" :class="iconClass">
        <Icon :name="tile.icon" class="size-6" />
      </span>
      <span
        v-if="tile.badge"
        class="rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums"
        :class="badgeClass"
        data-session-tile-badge
      >{{ tile.badge }}</span>
    </span>
    <span class="mt-auto">
      <span class="block text-sm font-semibold leading-tight">{{ tile.label }}</span>
      <span class="block text-xs" :class="descriptionClass">{{ tile.description }}</span>
    </span>
  </button>
</template>
