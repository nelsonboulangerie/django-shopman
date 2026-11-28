<script setup lang="ts">
// EXPERIMENT(duvida-no-ponto) remove_after 2027-02-20
// Componente inteiro da versão B do experimento `duvida-no-ponto` (OC-33 B3): as
// perguntas da FAQ que cabem neste ponto (a sacola), recolhidas.
// Pergunta e resposta são as da página /faq, lidas do `shell.faq` que o `app.vue` já
// buscou; quem decide se este componente aparece é a página, por `useExperience`.
import { faqAtPoint, type FaqPoint } from '~/presentation/faqAtPoint'
import type { ShellResponse } from '~/types/shopman'
import { STOREFRONT_SHELL_KEY } from '~/composables/useStorefrontShell'

const props = defineProps<{
  point: FaqPoint
}>()

const { data: shell } = useNuxtData<ShellResponse>(STOREFRONT_SHELL_KEY)
const items = computed(() => faqAtPoint(shell.value?.shell?.faq, props.point))
const headingId = computed(() => `faq-at-point-${props.point}`)
</script>

<template>
  <!-- EXPERIMENT(duvida-no-ponto) remove_after 2027-02-20 -->
  <section v-if="items.length" :aria-labelledby="headingId" :data-faq-point="point">
    <h2 :id="headingId" class="shop-heading">Dúvidas frequentes</h2>
    <UiAccordion
      :items="items.map(item => ({ value: item.ref, title: item.question, content: item.answer }))"
      type="single"
      collapsible
      class="mt-2 border-y"
    >
      <template #content="{ item }">
        <!-- A resposta é corpo de LEITURA: 16 px, como na home e na /faq (X9). -->
        <UiAccordionContent><p class="shop-reading whitespace-pre-line" :data-faq-point-answer="item.value">{{ item.content }}</p></UiAccordionContent>
      </template>
    </UiAccordion>
  </section>
</template>
