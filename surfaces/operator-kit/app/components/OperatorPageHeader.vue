<script setup lang="ts">
// Cabeçalho de uma linha (UX-KIT-V1, prévias v3/v4): título, "ao vivo" discreto, UMA
// busca e os controles da tela na mesma linha; os recortes (chips) na segunda. Mede o
// `<header>` de `orders-board3.html`: `px-4 pt-3 pb-2.5`, título de 22px, busca de
// 22rem, controles de 44px. Par do `OperatorSuiteRail`: com as seções no rail, o topo
// do conteúdo deixa de ter barra de seções.
//
// Por dispositivo:
//   - celular (abaixo de `md`): barra de 56px com o selo do app (volta à Central), o
//     título, o ponto ao vivo, a lupa (abre a busca numa linha própria), as ações de
//     polegar da tela (`#phone-actions`) e Avisos (a caixa do kit, V6-KIT). Os
//     controles (`#actions`) e os recortes (`#filters`) descem cada um para uma linha
//     que rola na horizontal. O selo e Avisos valem também no tablet em pé, onde o rail
//     dá lugar à barra de seções embaixo;
//   - a busca da tela é o `#search`; a busca da SUÍTE (frente BUSCA, peça
//     `OperatorSuiteSearch`) entra pelo mesmo lugar quando existir;
//   - tablet e desktop: a linha inteira. Os controles quebram para baixo antes de
//     espremer a busca (`flex-wrap`), sem rolagem horizontal da página.
//
// A busca é renderizada UMA vez (o atalho "/" segura a referência dela): no celular
// ela só muda de linha.
import { computed, nextTick, ref } from "vue";

import type { OperatorSession } from "../types/operator";

const props = withDefaults(defineProps<{
  title: string;
  /**
   * Linha fina acima do título. Omitida num dispositivo que é posto, ela diz o posto
   * ("Posto Saída · este dispositivo"), como na v4: o posto mora no cabeçalho, não num
   * ícone no rail.
   */
  eyebrow?: string;
  /**
   * A linha de recortes quebra em várias do tablet para cima (padrão). `false`: fica
   * numa linha só e rola na horizontal (ex.: as coleções do Catálogo).
   */
  filtersWrap?: boolean;
  /**
   * Mostra a caixa de Avisos na barra de 56px onde o rail não existe (celular e tablet
   * em pé). Padrão: sim, em toda tela; do tablet deitado para cima ela mora no rail.
   */
  inbox?: boolean;
}>(), { eyebrow: "", filtersWrap: true, inbox: true });

// A busca é lida de `$slots` no render, nunca num `computed`: `useSlots()` não é
// reativo, e um `computed` guardava a ausência do primeiro render (a tela que nasce
// sem busca e ganha uma depois ficava sem campo e sem lupa; V6 C01).

const config = useRuntimeConfig().public as { operatorHubUrl?: string };
const hubUrl = config.operatorHubUrl || "";

const { isCollapsed, set: setRail } = useRailState();
const railShown = useSuiteRailShown();

const { data: operatorSession } = useNuxtData<OperatorSession>("operator-session");
const eyebrowText = computed(() => {
  if (props.eyebrow) return props.eyebrow;
  const context = operatorSession.value?.workstation?.context_label ?? "";
  return context ? `${context} · este dispositivo` : "";
});

const searchOpen = ref(false);
const searchBox = ref<HTMLElement | null>(null);
function openSearch() {
  searchOpen.value = !searchOpen.value;
  if (!searchOpen.value) return;
  void nextTick(() => searchBox.value?.querySelector<HTMLInputElement>("input")?.focus());
}
</script>

<template>
  <header
    class="flex shrink-0 flex-col border-b border-border bg-card print:hidden"
    data-operator-page-header
  >
    <div class="flex flex-wrap items-center gap-x-3 gap-y-2 pr-2 pl-4 md:px-4 md:pt-3 md:pb-2.5">
      <!-- celular e tablet em pé: o selo do app (o rail não existe ali) -->
      <!-- Tela com caminho de volta (`#lead`): no celular o voltar ocupa o lugar do selo. -->
      <!-- O alvo de toque é de 44px (a régua da casa); o selo desenhado segue com 36. -->
      <OperatorAppSeal v-if="hubUrl && !$slots.lead" />

      <!-- tablet deitado/desktop com o rail oculto: o caminho de volta para ele -->
      <button
        v-if="isCollapsed"
        type="button"
        class="hidden size-control shrink-0 place-items-center rounded-md border border-border bg-card text-muted-foreground transition hover:bg-accent hover:text-foreground rail:grid"
        aria-label="Mostrar a barra"
        title="Mostrar a barra"
        data-page-header-show-rail
        @click="setRail('compact')"
      >
        <Icon name="lucide:panel-left-open" class="size-5" />
      </button>

      <slot name="lead" />

      <div class="flex min-w-0 flex-1 basis-0 items-center gap-3 py-2.5 md:flex-none md:basis-auto md:py-0">
        <div class="min-w-0">
          <p v-if="eyebrowText" class="op-eyebrow truncate text-muted-foreground" data-page-header-eyebrow>{{ eyebrowText }}</p>
          <h1 class="truncate text-[20px] leading-none font-semibold tracking-[-0.01em] md:text-[22px]">{{ title }}</h1>
          <!-- Linha fina SOB o título (prévias v4: "22:03 · sáb 03/10 · lotes fechados
               hoje"; no celular "06:12 · 6 para finalizar"). Opcional. -->
          <slot name="subtitle" />
        </div>
        <slot name="status" />
      </div>

      <div v-if="$slots.search" class="hidden w-1 md:block" aria-hidden="true" />
      <div
        v-if="$slots.search"
        ref="searchBox"
        class="order-last w-full pb-2.5 md:order-none md:w-auto md:pb-0"
        :class="searchOpen ? 'block pr-2' : 'hidden md:block'"
        data-page-header-search
      >
        <slot name="search" />
      </div>

      <div class="hidden flex-1 md:block" />

      <!-- celular: lupa e ações de polegar na barra de 56px -->
      <div class="flex items-center md:hidden">
        <button
          v-if="$slots.search"
          type="button"
          class="grid size-12 place-items-center rounded-md text-foreground"
          :aria-label="searchOpen ? 'Fechar a busca' : 'Buscar'"
          :aria-expanded="searchOpen"
          data-page-header-search-toggle
          @click="openSearch"
        >
          <Icon :name="searchOpen ? 'lucide:x' : 'lucide:search'" class="size-6" />
        </button>
        <slot name="phone-actions" />
      </div>

      <!-- No celular os controles da tela não somem: descem para uma linha própria,
           que rola na horizontal (nenhuma função fica só no desktop). -->
      <div
        v-if="$slots.actions"
        class="order-last -ml-4 flex w-[calc(100%+1.5rem)] items-center gap-2 overflow-x-auto px-4 pb-2.5 no-scrollbar *:shrink-0 md:order-none md:ml-0 md:w-auto md:flex-wrap md:justify-end md:overflow-visible md:px-0 md:pb-0"
        data-page-header-actions
      >
        <slot name="actions" />
      </div>

      <!-- Onde o rail não existe (celular e tablet em pé): os Avisos na barra de 56px,
           a mesma caixa do pé do rail (V6-KIT, T-06). Montada por script, não só
           escondida: duas caixas no DOM seriam dois "Avisos". -->
      <ClientOnly v-if="inbox">
        <div v-if="!railShown" class="-mr-1 flex shrink-0 items-center" data-page-header-inbox>
          <OperatorInbox placement="header" />
        </div>
      </ClientOnly>
    </div>

    <div
      v-if="$slots.filters"
      class="flex items-center gap-1.5 overflow-x-auto px-4 pb-2.5 no-scrollbar *:shrink-0"
      :class="filtersWrap ? 'md:flex-wrap md:overflow-visible' : ''"
      data-page-header-filters
    >
      <slot name="filters" />
    </div>
    <slot name="below" />
  </header>
</template>
