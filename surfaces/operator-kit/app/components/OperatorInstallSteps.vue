<script setup lang="ts">
// O passo a passo de instalação, desenhado para quem NÃO conhece o símbolo pelo nome.
//
// Três decisões, todas por causa da reclamação que originou o WP: um testador com mais
// idade — e nada leigo — não conseguiu seguir "toque em Compartilhar".
//
// 1. O símbolo aparece do lado do texto, do tamanho em que ele aparece na tela dela.
//    "Compartilhar" só é uma palavra para quem já sabe qual é o botão.
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
      <li v-for="(step, index) in plan.steps" :key="index" class="flex items-start gap-3">
        <span class="relative shrink-0">
          <span
            class="flex size-10 items-center justify-center rounded-md border border-border bg-muted text-foreground"
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
        <p class="pt-2 text-sm leading-snug text-foreground">
          <template v-for="(part, partIndex) in installTextParts(step.text)" :key="partIndex">
            <strong v-if="part.strong" class="font-semibold">{{ part.text }}</strong>
            <template v-else>{{ part.text }}</template>
          </template>
        </p>
      </li>
    </ol>

    <p v-if="plan.done" class="mt-3 text-sm font-medium text-foreground">
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
