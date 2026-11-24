<script setup lang="ts">
// As dúvidas frequentes na home. A versão padrão ("a") é a seção de sempre: as 6
// perguntas mais úteis (`HOME_FAQ_LIMIT`, OC-31) e "Ver todas as perguntas".
import type { CopyEntryProjection, FAQItemProjection } from '~/types/shopman'

defineProps<{
  faq: FAQItemProjection[]
  heading: CopyEntryProjection
}>()

// EXPERIMENT(duvida-no-ponto) remove_after 2027-02-20
const duvidaNoPonto = useExperience('duvida-no-ponto')
</script>

<template>
  <!-- Versão B: a resposta mora no ponto da dúvida (a sacola); a home
       fica só com o caminho para a página das perguntas. -->
  <!-- EXPERIMENT(duvida-no-ponto) remove_after 2027-02-20 -->
  <section v-if="duvidaNoPonto.is('b')" class="border-t bg-background py-6" data-home-faq-link>
    <div class="shop-container text-center">
      <UiButton to="/faq" variant="ghost" icon="lucide:arrow-right" icon-placement="right" class="shop-gold-hover">
        Dúvidas frequentes
      </UiButton>
    </div>
  </section>
  <section v-else id="duvidas-frequentes" class="shop-section border-t bg-background scroll-mt-20">
    <div class="shop-container">
      <div class="mx-auto max-w-4xl">
        <div class="text-center">
          <h2 class="shop-heading font-display">{{ heading.title }}</h2>
          <p v-if="heading.message" class="mt-2 shop-muted">
            {{ heading.message }}
          </p>
        </div>
        <UiAccordion
          :items="faq.map(item => ({ value: item.ref, title: item.question, content: item.answer }))"
          type="single"
          collapsible
          class="mt-6 border-y"
        >
          <template #content="{ item }">
            <!-- A resposta é corpo de LEITURA: 16 px, não os 14 do acordeão (X9, OC-30). -->
            <UiAccordionContent><p class="shop-reading whitespace-pre-line">{{ item.content }}</p></UiAccordionContent>
          </template>
        </UiAccordion>
        <div class="mt-4 text-center">
          <UiButton to="/faq" variant="ghost" icon="lucide:arrow-right" icon-placement="right" class="shop-gold-hover">
            Ver todas as perguntas
          </UiButton>
        </div>
      </div>
    </div>
  </section>
</template>
