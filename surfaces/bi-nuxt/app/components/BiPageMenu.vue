<script setup lang="ts">
// O ⋯ do cabeçalho (prévia `bi-sobra4.html`: "Mais: Exportar, Copiar link, Como é
// calculado"). O que se usa a cada leitura fica à vista; o resto mora aqui, a um toque.
// NuxtDropdownMenu canônico. "Copiar link" é de toda tela: a leitura inteira (período,
// dia, recortes) vive na URL. Itens próprios da tela entram por `items`.
import type { BiMenuItem } from "~/presentation/bi";

const props = withDefaults(defineProps<{ items?: BiMenuItem[] }>(), { items: () => [] });

const { run: copyLink } = usePendingAction(async () => {
  try {
    await navigator.clipboard.writeText(window.location.href);
    useSonner.success("Link copiado: quem abrir vê esta mesma leitura.");
  } catch {
    useSonner.warning("Não deu para copiar. O endereço na barra do navegador é o link desta leitura.");
  }
});

const menuItems = computed<BiMenuItem[]>(() => [
  { label: "Copiar link desta leitura", icon: "i-lucide-link", onSelect: () => void copyLink() },
  ...props.items,
]);

// O rótulo diz o que o menu tem. Antes ele dizia "e como é calculado" em todas as
// telas, e só a de Produção tinha esse item (omotenashi-copy: rótulo que mente).
const triggerLabel = computed(() =>
  props.items.length
    ? `Mais: copiar link e ${props.items.map((item) => item.label.toLowerCase()).join(", ")}`
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
      data-bi-page-menu
    />
  </NuxtDropdownMenu>
</template>
