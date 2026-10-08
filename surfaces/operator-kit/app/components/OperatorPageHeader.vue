<script setup lang="ts">
// Cabeçalho de uma linha (UX-KIT-V1, prévias v3/v4): título, "ao vivo" discreto, UMA
// busca e os controles da tela na mesma linha; os recortes (chips) na segunda. Mede o
// `<header>` de `orders-board3.html`: título, busca e ações no DashboardNavbar
// oficial. Os controles preservam o tamanho compacto do Nuxt UI no ponteiro fino;
// tamanhos e densidade continuam sendo os oficiais do Nuxt UI; ações realmente
// críticas de toque escolhem seu tamanho no componente que conhece o contexto.
// Par do `OperatorSuiteRail`: com as seções no rail, o topo do conteúdo deixa de ter
// barra de seções.
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
import { computed, onMounted, ref } from "vue";
import { useMediaQuery } from "@vueuse/core";

import { SUITE_MARKER_SELECTOR } from "../composables/useSuiteMarker";
import type { OperatorSession } from "../types/operator";

const props = withDefaults(
  defineProps<{
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
  }>(),
  {
    eyebrow: "",
    filtersWrap: true,
    inbox: true,
    search: true,
    searchPlaceholder: "Buscar pedido, cliente, produto ou tela",
  },
);

// A busca é lida de `$slots` no render, nunca num `computed`: `useSlots()` não é
// reativo, e um `computed` guardava a ausência do primeiro render (a tela que nasce
// sem busca e ganha uma depois ficava sem campo e sem lupa; V6 C01). Sem `#search`, a
// busca padrão da suíte (`search = true`).

const config = useRuntimeConfig().public as { operatorHubUrl?: string };
const hubUrl = config.operatorHubUrl || "";

const { isCollapsed, set: setRail } = useRailState();
const suiteRailMedia = useSuiteRailShown();
// Dentro do `OperatorSuiteShell`, o rail é o de três estados: o botão da barra o
// percorre (aberto, compacto, oculto) e Avisos sobe para a barra sempre que ele não
// está na tela. Fora do shell, a régua do `OperatorSuiteRail`.
const suiteRail = useSuiteRail();
const railShown = computed(() =>
  suiteRail ? suiteRail.visible.value : suiteRailMedia.value,
);

// Os controles (`#actions`) descem para uma linha própria no celular, como diz o
// contrato acima e como era no `main`. OPT-IN pela página que veste a suíte (os sete
// apps não migrados; ver `useSuiteMarker`): o Gestor decide no próprio app o que passa
// em `#actions` no celular e não muda (WP-OPERADOR-NUXTUI-ONDAS, onda 0). Sem isto, o
// período da Produção espremia a barra de 56px: a lupa cobria o selo do app (axe
// target-size) e a página rolava na horizontal.
const phone = useMediaQuery("(max-width: 767.98px)", { ssrWidth: 1280 });
const suitePage = ref(false);
onMounted(() => {
  suitePage.value = Boolean(document.querySelector(SUITE_MARKER_SELECTOR));
});
const actionsBelow = computed(() => suitePage.value && phone.value);

const { data: operatorSession } =
  useNuxtData<OperatorSession>("operator-session");
// O app pode dispensar o selo do posto (`operatorHeader.workstationBadge: false` no
// app.config) quando o título já diz a visão e o posto mora no menu do operador.
const appConfig = useAppConfig() as {
  operatorHeader?: { workstationBadge?: boolean };
};
const eyebrowText = computed(() => {
  if (props.eyebrow) return props.eyebrow;
  if (appConfig.operatorHeader?.workstationBadge === false) return "";
  const context = operatorSession.value?.workstation?.context_label ?? "";
  return context ? `${context} · este dispositivo` : "";
});

const { request: openSearch } = useSuiteSearchRequest();
</script>

<template>
  <NuxtDashboardNavbar
    as="header"
    :toggle="Boolean(suiteRail)"
    class="print:hidden"
    data-operator-page-header
  >
    <template #leading>
      <OperatorAppSeal v-if="hubUrl && !$slots.lead" />
      <NuxtButton
        v-if="suiteRail"
        class="hidden lg:inline-flex"
        :icon="suiteRail.next.value.icon"
        color="neutral"
        variant="ghost"
        square
        :aria-label="suiteRail.next.value.label"
        :title="suiteRail.next.value.label"
        data-rail-cycle
        @click="suiteRail.cycle()"
      />
      <NuxtButton
        v-else-if="isCollapsed"
        class="hidden rail:inline-flex"
        icon="i-lucide-panel-left-open"
        color="neutral"
        variant="ghost"
        square
        aria-label="Mostrar a barra lateral"
        title="Mostrar a barra lateral"
        data-page-header-show-rail
        @click="setRail('compact')"
      />
      <slot name="lead" />
    </template>

    <template #title>
      <span>{{ title }}</span>
      <NuxtBadge
        v-if="eyebrowText"
        color="neutral"
        data-page-header-eyebrow
        >{{ eyebrowText }}</NuxtBadge
      >
    </template>

    <template #trailing>
      <slot name="subtitle" />
      <slot name="status" />
    </template>

    <template v-if="$slots.search || search" #default>
      <div class="w-full" data-page-header-search>
        <slot name="search"
          ><OperatorSuiteSearch :placeholder="searchPlaceholder"
        /></slot>
      </div>
    </template>

    <template #right>
      <NuxtButton
        v-if="$slots.search || search"
        class="lg:hidden suite-page:size-control suite-page:justify-center"
        color="neutral"
        variant="ghost"
        icon="i-lucide-search"
        square
        aria-label="Buscar"
        aria-haspopup="dialog"
        data-page-header-search-toggle
        @click="openSearch"
      />
      <slot name="phone-actions" />
      <div
        v-if="$slots.actions && !actionsBelow"
        class="flex items-center gap-2"
        data-page-header-actions
      >
        <slot name="actions" />
      </div>
      <ClientOnly v-if="inbox">
        <div
          v-if="!railShown"
          class="flex shrink-0 items-center"
          data-page-header-inbox
        >
          <OperatorInbox placement="header" />
        </div>
      </ClientOnly>
    </template>
  </NuxtDashboardNavbar>

  <NuxtDashboardToolbar v-if="$slots.actions && actionsBelow" class="py-2">
    <div
      class="flex w-full items-center gap-2 flex-nowrap overflow-x-auto no-scrollbar [&>*]:shrink-0"
      data-page-header-actions
    >
      <slot name="actions" />
    </div>
  </NuxtDashboardToolbar>

  <NuxtDashboardToolbar v-if="$slots.filters" class="py-2">
    <div
      class="flex w-full items-center gap-2"
      :class="
        filtersWrap
          ? 'flex-wrap'
          : 'flex-nowrap overflow-x-auto no-scrollbar [&>*]:shrink-0'
      "
      data-page-header-filters
    >
      <slot name="filters" />
    </div>
  </NuxtDashboardToolbar>

  <!-- Navegação secundária da tela (as abas de Ajustes do PDV, o prazo do anúncio no
       Marketing, a seção do Compras no celular). Vue descarta slot não declarado sem
       aviso: sem esta linha, as abas de Ajustes do PDV somem. -->
  <slot name="below" />

  <!-- Feedback contextual não é controle de toolbar. Ações, filtros, contagens e
       freshness pertencem ao slot #filters e, portanto, à DashboardToolbar oficial. -->
  <div
    v-if="$slots.feedback"
    class="px-4 py-2 sm:px-6"
    data-page-header-feedback
  >
    <slot name="feedback" />
  </div>
</template>
