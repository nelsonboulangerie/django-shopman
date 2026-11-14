<script setup lang="ts">
// O passo a passo de instalação, desenhado para quem NÃO conhece o símbolo pelo nome.
//
// Três decisões, todas por causa da reclamação que originou o WP: um testador com mais
// idade — e nada leigo — não conseguiu seguir "toque em Compartilhar".
//
// 1. O passo tem duas linhas (dono, 14/11): o gesto em cima ("Role e toque em"), o
//    símbolo com o rótulo embaixo. O símbolo fica colado na palavra que ele nomeia, e os
//    dois centrados na mesma linha: dentro da frase, ele quebrava a linha e desalinhava.
// 2. O rótulo literal do menu vem em negrito, escrito exatamente como o navegador
//    escreve. O olho procura a palavra, não a frase.
// 3. Curto: o desenho mostra o botão, então a frase não o descreve.
import { INSTALL_GLYPH_PATHS, installStepLines, installTextParts, type InstallPlan } from "../utils/installGuide";

defineProps<{ plan: InstallPlan }>();
</script>

<template>
  <div v-if="plan.steps.length" data-operator-install-steps>
    <ol class="space-y-3">
      <li v-for="(step, index) in plan.steps" :key="index" class="flex items-start gap-2 text-sm">
        <span class="w-4 shrink-0 text-right tabular-nums leading-6 text-muted-foreground">{{ index + 1 }}.</span>
        <div class="min-w-0 space-y-1">
          <p v-if="installStepLines(step.text, step.glyph).lead.length" class="leading-6 text-foreground">
            <template v-for="(part, partIndex) in installStepLines(step.text, step.glyph).lead" :key="partIndex">
              <strong v-if="part.strong" class="font-semibold">{{ part.text }}</strong>
              <template v-else>{{ part.text }}</template>
            </template>
          </p>
          <p class="flex flex-wrap items-center gap-x-2 gap-y-1 text-foreground" data-install-step-target>
            <template v-for="(part, partIndex) in installStepLines(step.text, step.glyph).target" :key="partIndex">
              <span
                v-if="part.glyph"
                class="inline-grid size-7 shrink-0 place-items-center rounded-md border border-border bg-muted text-foreground"
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
              <strong v-if="part.strong && part.text" class="font-semibold">{{ part.text }}</strong>
              <span v-else-if="part.text.trim()">{{ part.text.trim() }}</span>
            </template>
          </p>
        </div>
      </li>
    </ol>

    <p v-if="plan.note" class="mt-3 text-xs leading-snug text-muted-foreground">
      <template v-for="(part, partIndex) in installTextParts(plan.note)" :key="partIndex">
        <strong v-if="part.strong" class="font-semibold">{{ part.text }}</strong>
        <template v-else>{{ part.text }}</template>
      </template>
    </p>
  </div>
</template>
