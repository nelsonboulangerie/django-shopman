<script setup lang="ts">
// O passo a passo de instalação, desenhado para quem NÃO conhece o símbolo pelo nome.
//
// A tela anterior tinha dois passos em carrossel, com um desenho de iPhone e a frase
// "Toque em Compartilhar na barra do Safari" — verdadeira só no Safari, e mostrada para
// todo mundo em iOS.
//
// Três decisões, todas por causa da reclamação que originou o WP: um testador com mais
// idade — e nada leigo — não conseguiu seguir aquilo.
//
// 1. O símbolo aparece do lado do texto. "Compartilhar" só é uma palavra para quem já
//    sabe qual é o botão.
// 2. O rótulo literal do menu vem em negrito, escrito como o navegador escreve.
// 3. Os passos aparecem todos de uma vez, numerados. O carrossel escondia o passo 2 e
//    pedia um toque a mais para descobrir o tamanho da tarefa.
import { INSTALL_GLYPH_PATHS, installTextParts, type InstallPlan } from '~/utils/installGuide'

defineProps<{ plan: InstallPlan }>()
</script>

<template>
  <div v-if="plan.steps.length" class="px-4 pt-2 pb-1" data-testid="pwa-install-steps">
    <ol class="space-y-4">
      <li v-for="(step, index) in plan.steps" :key="index" class="flex items-start gap-3">
        <span class="relative shrink-0">
          <span
            class="flex size-11 items-center justify-center rounded-lg border border-primary/15 bg-[#fcf7ee] text-primary"
            aria-hidden="true"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              class="size-6"
            >
              <path v-for="(d, glyphIndex) in INSTALL_GLYPH_PATHS[step.glyph]" :key="glyphIndex" :d="d" />
            </svg>
          </span>
          <span
            class="absolute -top-1.5 -left-1.5 flex size-5 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
          >
            {{ index + 1 }}
          </span>
        </span>
        <p class="shop-body pt-2 leading-snug">
          <template v-for="(part, partIndex) in installTextParts(step.text)" :key="partIndex">
            <strong v-if="part.strong" class="font-semibold">{{ part.text }}</strong>
            <template v-else>{{ part.text }}</template>
          </template>
        </p>
      </li>
    </ol>

    <p v-if="plan.done" class="shop-body mt-4 font-semibold">{{ plan.done }}</p>
    <p v-if="plan.note" class="shop-meta mt-2 leading-snug">
      <template v-for="(part, partIndex) in installTextParts(plan.note)" :key="partIndex">
        <strong v-if="part.strong" class="font-semibold">{{ part.text }}</strong>
        <template v-else>{{ part.text }}</template>
      </template>
    </p>
  </div>
</template>
