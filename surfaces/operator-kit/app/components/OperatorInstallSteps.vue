<script setup lang="ts">
// O passo a passo de instalação, desenhado para quem NÃO conhece o símbolo pelo nome.
//
// Três decisões, todas por causa da reclamação que originou o WP: um testador com mais
// idade — e nada leigo — não conseguiu seguir "toque em Compartilhar".
//
// 1. O símbolo entra DENTRO da frase, colado no rótulo que ele nomeia:
//    "Toque em [⬆] **Compartilhar**". "Compartilhar" só é uma palavra para quem já sabe
//    qual é o botão, e o desenho numa coluna à parte obrigava o olho a atravessar a
//    linha carregando o significado. O número volta a ser o que ele é em qualquer
//    lista — o marcador —, em vez de disputar com o desenho o papel de marcador.
// 2. O rótulo literal do menu vem em negrito, escrito exatamente como o navegador
//    escreve. O olho procura a palavra, não a frase.
// 3. O fim é dito: `plan.done` conta o que ela vai ver quando terminar. Instrução que
//    não diz onde termina deixa a pessoa em dúvida se deu certo.
import { INSTALL_GLYPH_PATHS, installTextParts, type InstallPlan } from "../utils/installGuide";

defineProps<{ plan: InstallPlan }>();
</script>

<template>
  <div v-if="plan.steps.length" data-operator-install-steps>
    <ol class="space-y-4">
      <li v-for="(step, index) in plan.steps" :key="index" class="flex items-start gap-2">
        <span class="w-4 shrink-0 text-right text-sm tabular-nums text-muted-foreground">{{ index + 1 }}.</span>
        <p class="text-sm leading-loose text-foreground">
          <template v-for="(part, partIndex) in installTextParts(step.text, step.glyph)" :key="partIndex">
            <span
              v-if="part.glyph"
              class="mr-1 inline-grid size-7 translate-y-2 place-items-center rounded-md border border-border bg-muted align-baseline text-foreground"
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

    <p v-if="plan.done" class="mt-4 text-sm font-medium text-foreground">
      {{ plan.done }}
    </p>
    <p v-if="plan.note" class="mt-2 text-xs leading-snug text-muted-foreground">
      <template v-for="(part, partIndex) in installTextParts(plan.note)" :key="partIndex">
        <strong v-if="part.strong" class="font-semibold">{{ part.text }}</strong>
        <template v-else>{{ part.text }}</template>
      </template>
    </p>
  </div>
</template>
