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
// 1. O símbolo entra DENTRO da frase, colado no rótulo que ele nomeia. "Compartilhar"
//    só é uma palavra para quem já sabe qual é o botão — e o desenho numa coluna à
//    parte disputava com o número o papel de marcador, que é o defeito que o dono
//    apontou: o olho não sabia se o número fazia parte do símbolo.
// 2. O rótulo literal do menu vem em negrito, escrito como o navegador escreve.
// 3. Os passos aparecem todos de uma vez, numerados. O carrossel escondia o passo 2 e
//    pedia um toque a mais para descobrir o tamanho da tarefa.
import { INSTALL_GLYPH_PATHS, installTextParts, type InstallPlan } from '~/utils/installGuide'

defineProps<{ plan: InstallPlan }>()
</script>

<template>
  <div v-if="plan.steps.length" class="px-4 pt-2 pb-1" data-testid="pwa-install-steps">
    <ol class="space-y-4">
      <li v-for="(step, index) in plan.steps" :key="index" class="flex items-start gap-2">
        <span class="shop-body w-4 shrink-0 text-right tabular-nums text-muted-foreground">{{ index + 1 }}.</span>
        <p class="shop-body leading-loose">
          <template v-for="(part, partIndex) in installTextParts(step.text, step.glyph)" :key="partIndex">
            <span
              v-if="part.glyph"
              class="mr-1 inline-grid size-7 translate-y-2 place-items-center rounded-md border border-primary/15 bg-[#fcf7ee] align-baseline text-primary"
              aria-hidden="true"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                class="size-4"
              >
                <path v-for="(d, glyphIndex) in INSTALL_GLYPH_PATHS[part.glyph]" :key="glyphIndex" :d="d" />
              </svg>
            </span>
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
