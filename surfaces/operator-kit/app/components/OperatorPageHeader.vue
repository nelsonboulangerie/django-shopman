<script setup lang="ts">
// Cabeçalho de uma linha (UX-KIT-V1, prévias v3/v4): título, "ao vivo" discreto, UMA
// busca e os controles da tela na mesma linha; os recortes (chips) na segunda. Mede o
// `<header>` de `orders-board3.html`: `px-4 pt-3 pb-2.5`, título de 22px, busca de
// 22rem, controles de 44px. Par do `OperatorSuiteRail`: com as seções no rail, o topo
// do conteúdo deixa de ter barra de seções.
//
// Por dispositivo:
//   - celular (abaixo de `md`): barra de 56px com o selo do app (volta à Central), o
//     título, o ponto ao vivo, a lupa (abre a busca da suíte em tela cheia), as ações de
//     polegar da tela (`#phone-actions`) e Avisos (a caixa do kit, V6-KIT). Os
//     controles (`#actions`) e os recortes (`#filters`) descem cada um para uma linha
//     que rola na horizontal. O selo e Avisos valem também no tablet em pé, onde o rail
//     dá lugar à barra de seções embaixo;
//   - tablet e desktop: a linha inteira. Os controles quebram para baixo antes de
//     espremer a busca (`flex-wrap`), sem rolagem horizontal da página.
//
// A busca é UMA, a da suíte (`OperatorSuiteSearch`, V6-BUSCA): toda tela a tem no
// cabeçalho. A tela que filtra a própria lista passa a sua no `#search` (com `v-model`,
// o alcance "Esta tela"); as outras ganham a padrão. No celular a lupa a abre em tela
// cheia.
import { computed } from "vue";

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
  /** `false` só onde a tela não é lugar de trabalho (não há hoje). */
  search?: boolean;
  /** O texto do campo da busca padrão (sem filtro próprio da tela). */
  searchPlaceholder?: string;
}>(), { eyebrow: "", filtersWrap: true, inbox: true, search: true, searchPlaceholder: "Buscar pedido, cliente, produto ou tela" });

// A busca é lida de `$slots` no render, nunca num `computed`: `useSlots()` não é
// reativo, e um `computed` guardava a ausência do primeiro render (a tela que nasce
// sem busca e ganha uma depois ficava sem campo e sem lupa; V6 C01). Sem `#search`, a
// busca padrão da suíte (`search = true`).

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

const { request: openSearch } = useSuiteSearchRequest();
</script>

<template>
  <header
    class="flex min-h-[var(--op-header-min-height)] shrink-0 flex-col border-b border-border bg-card print:hidden"
    data-operator-page-header
  >
    <div class="flex flex-wrap items-center gap-x-2 gap-y-2 pr-2 pl-4 md:gap-x-3 md:px-4 md:pt-3 md:pb-2.5">
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

      <div class="flex min-w-0 flex-1 basis-0 items-center gap-2 py-2.5 md:flex-none md:basis-auto md:gap-3 md:py-0">
        <div class="min-w-0">
          <p v-if="eyebrowText" class="op-eyebrow truncate text-muted-foreground" data-page-header-eyebrow>{{ eyebrowText }}</p>
          <h1 class="truncate text-[19px] leading-none font-semibold tracking-[-0.01em] outline-none md:text-[22px]">{{ title }}</h1>
          <!-- Linha fina SOB o título (prévias v4: "22:03 · sáb 03/10 · lotes fechados
               hoje"; no celular "06:12 · 6 para finalizar"). Opcional. -->
          <slot name="subtitle" />
        </div>
        <slot name="status" />
      </div>

      <div v-if="$slots.search || search" class="hidden w-1 md:block" aria-hidden="true" />
      <div
        v-if="$slots.search || search"
        class="hidden md:block md:w-auto"
        data-page-header-search
      >
        <slot name="search"><OperatorSuiteSearch :placeholder="searchPlaceholder" /></slot>
      </div>

      <div class="hidden flex-1 md:block" />

      <!-- celular: lupa e ações de polegar na barra de 56px -->
      <div class="flex items-center md:hidden">
        <button
          v-if="$slots.search || search"
          type="button"
          class="grid size-11 place-items-center rounded-md text-foreground md:size-12"
          aria-label="Buscar"
          aria-haspopup="dialog"
          data-page-header-search-toggle
          @click="openSearch"
        >
          <Icon name="lucide:search" class="size-6" />
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
