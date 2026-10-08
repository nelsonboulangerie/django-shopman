<script setup lang="ts">
// O ⋯ do cabeçalho de uma página de leitura (PR-K1 do WP-BI-CANON-LAUDO, item C2).
// Promovido do `BiPageMenu` do B.I. "Copiar link desta leitura" é de toda página
// de leitura: o período, o dia e os recortes vivem na URL, então o endereço É a
// leitura. Ações próprias da página entram por `items`, no mesmo menu.
import type { DropdownMenuItem } from "@nuxt/ui";
import { computed } from "vue";

import { usePendingAction } from "../composables/usePendingAction";

const props = withDefaults(defineProps<{ items?: DropdownMenuItem[] }>(), { items: () => [] });

const { run: copyLink } = usePendingAction(async () => {
  try {
    await navigator.clipboard.writeText(window.location.href);
    useSonner.success("Link copiado: quem abrir vê esta mesma leitura.");
  } catch {
    useSonner.warning("Não deu para copiar. O endereço na barra do navegador é o link desta leitura.");
  }
});

const menuItems = computed<DropdownMenuItem[]>(() => [
  { label: "Copiar link desta leitura", icon: "i-lucide-link", onSelect: () => void copyLink() },
  ...props.items,
]);

// O rótulo diz o que o menu tem (omotenashi-copy: rótulo que mente).
const triggerLabel = computed(() =>
  props.items.length
    ? `Mais: copiar link e ${props.items.map((item) => String(item.label ?? "").toLowerCase()).join(", ")}`
    : "Mais: copiar link desta leitura",
);
</script>

<template>
  <NuxtDropdownMenu :items="menuItems" :content="{ align: 'end' }">
    <NuxtButton
      icon="i-lucide-ellipsis"
      color="neutral"
      variant="ghost"
      square
      :aria-label="triggerLabel"
      data-operator-reading-page-menu
    />
  </NuxtDropdownMenu>
</template>
