<script setup lang="ts">
// A barra inferior do celular no shell da suíte: o menu RÁPIDO (dono, 08/10/2026,
// PR #1544). A gaveta (☰, a barra lateral) é o menu completo; aqui ficam de 3 a 5
// vagas, pela regra única de `quickBarLayout` (`suiteChrome.ts`), e uma delas vira
// "Mais" (abre a gaveta) só quando sobra seção.
//
// O desenho é o exemplo oficial "With bottom tab bar" do NavigationMenu
// (https://ui.nuxt.com/docs/components/navigation-menu#with-bottom-tab-bar): ícone em
// cima, rótulo embaixo, ativo pelo `active` do item. O `:ui` desse exemplo mora AQUI,
// uma vez para a suíte inteira, nunca nas telas. Do kit somam-se a fixação embaixo
// (fim da coluna de conteúdo), a área segura do iPhone e o alvo de toque mínimo
// (`min-h-control`). O tamanho do rótulo é o valor da documentação, exceção declarada
// no teto da trava do conjunto mínimo (`guardrails.minimalSet.test.ts`).
//
// O sinal de cada seção é o MESMO da barra lateral: o chip do item (ponto, ou número
// `4xl` com `inset: false`), e a descrição "Seção · N pendências" / "Seção · estado".
import { computed } from "vue";

import type { OperatorSection } from "../presentation/appBar";
import { quickBarLayout, railSignalChip, sectionDescription, sectionRailSignal } from "../presentation/suiteChrome";

const props = defineProps<{
  sections: readonly OperatorSection[];
  label: string;
  /** A seção ativa (a chave). */
  current?: string;
}>();

const emit = defineEmits<{ select: [key: string]; more: [] }>();

/**
 * O exemplo oficial, mais o alvo de toque do kit no link e os itens espalhados por
 * igual na largura (decisão do dono, 08/10: no exemplo literal eles se juntam no
 * centro, longe do polegar).
 */
const QUICK_BAR_UI = {
  // O Reka põe um <div> entre o root e a lista; ele precisa crescer para a lista
  // ocupar a largura (o root do Nuxt UI já mira esse filho com `[&>div]:min-w-0`).
  root: "justify-around border-t border-default py-2 [&>div]:flex-1",
  list: "w-full",
  item: "py-0 flex-1",
  link: "w-full flex-col gap-1 px-3 min-h-control justify-center",
  linkLeadingIcon: "size-5",
  linkLabel: "text-[10px]/3 font-normal",
};

const layout = computed(() => quickBarLayout(props.sections));

const items = computed(() => [
  ...layout.value.items.map((section) => {
    const signal = sectionRailSignal(section);
    return {
      label: section.shortLabel || section.label,
      icon: section.icon,
      to: section.to,
      active: props.current === section.key,
      chip: signal ? railSignalChip(signal) : undefined,
      "aria-label": sectionDescription(section),
      "data-section": section.key,
      onSelect: section.to ? undefined : () => emit("select", section.key),
    };
  }),
  ...(layout.value.more
    ? [
        {
          label: "Mais",
          icon: "i-lucide-menu",
          "aria-label": "Mais: o menu completo",
          "data-quick-bar-more": "",
          onSelect: () => emit("more"),
        },
      ]
    : []),
]);
</script>

<template>
  <!-- O NavigationMenu já é o `<nav>` (com o nome); este invólucro só fixa, guarda a
       área segura e some do `lg` para cima, onde a barra lateral está na tela. -->
  <div
    class="shrink-0 bg-default pb-[env(safe-area-inset-bottom)] lg:hidden print:hidden"
    data-operator-suite-tabs
    data-focus-obstruction
  >
    <NuxtNavigationMenu
      class="w-full"
      orientation="horizontal"
      :items="items"
      :ui="QUICK_BAR_UI"
      :aria-label="label"
      data-operator-quick-bar
    />
  </div>
</template>
