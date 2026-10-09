<script setup lang="ts">
// O chip de contagem da suíte NO FLUXO (dono, 09/10/2026): na ponta direita da linha,
// no centro vertical. Botão, aba, recorte com contagem, item da barra lateral aberta.
// No canto do ícone (barra compactada, barra inferior) o mesmo desenho sai do `chip`
// do item do NavigationMenu, por `countChipProps`. Desenho e regras em
// `presentation/countChip.ts`; README "Chip de contagem".
//
// É o `NuxtChip` canônico, `standalone` + `inset`: no fluxo da linha, sem o deslocamento
// de meio chip do canto. O tamanho (`4xl`, 16 px) e o anel de 2 px vêm do `chip` do
// app.config. O anel no fluxo é `ring-transparent` (o único `:ui` desta peça, e mora
// aqui, uma vez no kit), e é isso que o põe na cor do fundo do
// pai em qualquer pai: o fundo do botão dourado ativo, o do recorte `soft` translúcido,
// a linha ativa da barra lateral, o hover. No fluxo o chip não cobre nada; o anel com a
// cor de um fundo fixo (`ring-bg`) aparecia como aro onde o pai tem outro fundo. No canto
// do ícone o anel continua `ring-bg`, porque lá ele separa o chip do ícone.
//
// Sobre pai preenchido de cor próxima (aba ativa dourada, barra lateral clara), o chip
// inverte: círculo na cor do texto do pai, número na cor do fundo do pai
// (`COUNT_CHIP_INVERTED_ON` em `presentation/countChip.ts`).
//
// Sem `count` maior que zero, nada aparece; `dot` desenha o ponto de estado (sem número)
// no tamanho padrão do ponto (`dotSize`, o do NavigationMenu quando vem dele).
import type { ChipProps } from "@nuxt/ui";
import { computed, useAttrs } from "vue";
import {
  COUNT_CHIP_COLOR,
  COUNT_CHIP_INVERT_CLASSES,
  COUNT_CHIP_SIZE,
  countChipText,
  hasCount,
  type CountChipColor,
} from "../presentation/countChip";

// O NuxtChip entrega os atributos ao filho do slot padrão, e aqui não há filho: os
// atributos (`data-*`, `aria-*`) vão no número (slot `content`); a classe, na raiz.
defineOptions({ inheritAttrs: false });
const attrs = useAttrs();
const passThrough = computed(() =>
  Object.fromEntries(Object.entries(attrs).filter(([name]) => name !== "class")),
);

const props = withDefaults(
  defineProps<{
    count?: number | null;
    color?: CountChipColor;
    /** Ponto de estado, sem número. */
    dot?: boolean;
    dotSize?: ChipProps["size"];
  }>(),
  { count: null, color: COUNT_CHIP_COLOR, dot: false, dotSize: "md" },
);

const shown = computed(() => props.dot || hasCount(props.count));
const numbered = computed(() => !props.dot && hasCount(props.count));
const size = computed<ChipProps["size"]>(() => (numbered.value ? COUNT_CHIP_SIZE : props.dotSize));
// Anel transparente (no fluxo) e a inversão sobre pai preenchido de cor próxima.
const chipUi = { base: `ring-transparent ${COUNT_CHIP_INVERT_CLASSES}` };
const text = computed(() => (numbered.value ? countChipText(props.count as number) : ""));
</script>

<template>
  <NuxtChip
    v-if="shown"
    as="span"
    :class="attrs.class"
    :color="color"
    :size="size"
    inset
    standalone
    :ui="chipUi"
  >
    <template #content>
      <span v-bind="passThrough" class="tabular-nums" data-count-chip>{{ text }}</span>
    </template>
  </NuxtChip>
</template>
