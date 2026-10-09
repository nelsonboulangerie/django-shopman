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
// Celular (abaixo de `sm`), a regra única da barra do topo e da toolbar
// (`presentation/pageHeader.ts`, README "Barra do topo no celular" e "Toolbar no
// celular"): ☰, o título (quebra, nunca corta) e no máximo 2 ícones fixos (Avisos e a
// Busca, ou a ação da tela de `priority` menor); todo o resto das `actions` vai para UM
// ⋯ "Mais ações". O `#status` (e o posto do dispositivo) desce para uma segunda linha da
// barra, nunca se espreme ao lado do título. No shell, o selo do app sai da barra (a
// gaveta já o tem). A toolbar é uma linha só: `#filters-primary` e `#filters-end` (até
// 2 controles somados; o `end` é a leitura, como o frescor, que na mesa fica no fim da
// linha) e "Filtros", que abre `#filters` num painel de baixo; os recortes ativos
// (`active-filters`) viram chips removíveis logo abaixo.
//
// A busca é UMA, a da suíte (`OperatorSuiteSearch`, V6-BUSCA): toda tela a tem no
// cabeçalho. A tela que filtra a própria lista passa a sua no `#search` (com `v-model`,
// o nível "Nesta tela"); as outras ganham a padrão. No celular a lupa a abre em tela
// cheia.
import { computed, onMounted, ref, useSlots } from "vue";
import { useScreen } from "../composables/useScreen";

import { SUITE_MARKER_SELECTOR } from "../composables/useSuiteMarker";
import {
  filtersButtonLabel,
  phoneHeaderLayout,
  type OperatorActiveFilter,
  type OperatorHeaderAction,
} from "../presentation/pageHeader";
import {
  SCREEN_ALERTS_VISIBLE,
  moreAlertsLabel,
  screenAlertIcon,
  type OperatorScreenAlert,
} from "../presentation/screenState";
import type { OperatorSession } from "../types/operator";

const props = withDefaults(
  defineProps<{
    title: string;
    /**
     * O título mais curto do celular (abaixo de `sm`), escolhido pelo CSS: o servidor
     * desenha os dois e cada largura mostra o seu (o pedido: "Pedido W01" na mesa, "W01"
     * no celular).
     */
    phoneTitle?: string;
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
    /**
     * As ações da tela, declaradas como dados (regra da barra do topo no celular). Do
     * `sm` para cima, um ⋯ com todas (ao lado do `#actions`, que segue como está).
     * Abaixo do `sm`, as de `priority` disputam a vaga de ícone com a Busca; as outras
     * vão para o ⋯ "Mais ações", na ordem declarada. A tela que declara `actions` tem o
     * `#actions` escondido no celular: o que importa no polegar está aqui.
     */
    actions?: OperatorHeaderAction[];
    /**
     * As ações só do celular (abaixo de `sm`): a vaga de ícone e o ⋯ "Mais ações", como
     * `actions`, mas do `sm` para cima não há ⋯ delas (lá o `#actions` e a toolbar já as
     * mostram). É o que o Gestor passava como `isNarrow ? [...] : undefined`: declarado
     * sempre, o servidor já desenha a barra do celular no primeiro desenho.
     */
    phoneActions?: OperatorHeaderAction[];
    /**
     * A partir de que largura o `#actions` aparece, decidido pelo CSS (nunca por `v-if`
     * com a régua do JS, que responde "mesa" até montar). Padrão: `sm` quando a tela
     * declara `actions`/`phone-actions`, senão sempre. `md`: a tela que tem o seu
     * celular até o `md` (`#phone-actions`, o painel próprio da fila do Gestor).
     */
    actionsFrom?: "sm" | "md";
    /** O nome do ⋯ (o que ele guarda). */
    actionsLabel?: string;
    /** Recortes ativos: o número no "Filtros" e os chips removíveis abaixo da linha. */
    activeFilters?: OperatorActiveFilter[];
    /** "Limpar" do painel de filtros. Padrão: remove cada recorte ativo. */
    clearFilters?: () => void;
    /**
     * Os avisos da tela (o que a tela precisa que a pessoa saiba agora), abaixo da
     * toolbar. O primeiro aparece inteiro; os outros ficam em "e mais N". Erro de rede é
     * do `OfflineBanner`; aviso com prazo, do `OperatorUrgentAlert`; erro de carregar o
     * conteúdo, do `OperatorScreenState`.
     */
    alerts?: OperatorScreenAlert[];
    /**
     * A toolbar no celular: `drawer` (uma linha, "Filtros" abre o painel; padrão no
     * shell da suíte) ou `row` (a linha de sempre, para os apps ainda fora do shell até
     * a onda de cada um).
     */
    phoneFilters?: "drawer" | "row";
    /**
     * `#filters` só do `sm` para cima (no shell): no celular não há "Filtros" nem painel,
     * porque o que a tela põe ali são ações, e elas já estão nas `phone-actions`.
     * `#filters-primary` e `#filters-end` seguem na linha do celular.
     */
    deskOnlyFilters?: boolean;
  }>(),
  {
    eyebrow: "",
    phoneTitle: "",
    filtersWrap: true,
    inbox: true,
    search: true,
    searchPlaceholder: "Buscar pedido, cliente, produto ou tela",
    actions: undefined,
    phoneActions: undefined,
    actionsFrom: undefined,
    actionsLabel: "Mais ações",
    activeFilters: () => [],
    clearFilters: undefined,
    phoneFilters: undefined,
    deskOnlyFilters: false,
    alerts: () => [],
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
const screen = useScreen();
const phone = screen.belowMd;
const suitePage = ref(false);
onMounted(() => {
  suitePage.value = Boolean(document.querySelector(SUITE_MARKER_SELECTOR));
});
const actionsBelow = computed(() => suitePage.value && phone.value);

// A régua do celular da barra do topo e da toolbar: abaixo de `sm`. A do kit
// (`useScreen`) responde "mesa" até a hidratação terminar; por isso a barra e a toolbar
// NÃO decidem por ela o primeiro desenho. Antes de hidratar, as duas variantes (celular
// e mesa) vão no HTML e o CSS mostra a certa (`sm:hidden` / `max-sm:hidden`): o celular
// já nasce no layout do celular, sem o flash da mesa e sem mismatch. Depois de
// hidratar, a variante que não serve sai da árvore (DOM enxuto, sem seletor em dobro).
const narrow = screen.belowSm;
const phoneVariant = computed(() => !screen.ready.value || narrow.value);
const deskVariant = computed(() => !screen.ready.value || !narrow.value);

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

// Barra do topo no celular. Avisos ocupa uma vaga onde a barra lateral não está na
// tela (abaixo de `sm` ela nunca está).
const slots = useSlots();
const declaredActions = computed(() => props.actions ?? []);
const phoneDeclared = computed(() => props.phoneActions ?? declaredActions.value);
const phoneLayout = computed(() =>
  phoneHeaderLayout({
    search: props.search || Boolean(slots.search),
    inbox: props.inbox,
    actions: phoneDeclared.value,
  }),
);
function menuItem(action: OperatorHeaderAction & { search?: true }) {
  // `priority` e `search` são do kit: o `OperatorMoreMenu` os tira do item.
  return action.search ? { ...action, onSelect: () => openSearch() } : action;
}
// Dois ⋯, um por variante, escolhidos pelo CSS: o do celular com o que não ganhou vaga,
// o da mesa com as `actions` declaradas.
const phoneMenuItems = computed(() => phoneLayout.value.overflow.map(menuItem));
const deskMenuItems = computed(() => declaredActions.value.map(menuItem));
const optedIn = computed(
  () => props.actions !== undefined || props.phoneActions !== undefined,
);
const actionsClass = computed(() => {
  const from = props.actionsFrom ?? (optedIn.value ? "sm" : undefined);
  return from === "md" ? "max-md:hidden" : from === "sm" ? "max-sm:hidden" : "";
});

// No shell, o selo do app sai da barra do celular: a gaveta (☰) o mostra no topo.
const sealClass = computed(() => (suiteRail ? "max-sm:hidden" : ""));

// Toolbar no celular.
const filtersMode = computed(
  () => props.phoneFilters ?? (suiteRail ? "drawer" : "row"),
);
const drawerMode = computed(() => filtersMode.value === "drawer");
// A linha do celular (no shell) e a toolbar da mesa: as duas antes de hidratar, cada
// uma com a sua classe de tela; depois, só a que serve. Funções lidas no render, não
// `computed`: `useSlots()` não é reativo (ver a busca, acima).
function phoneFilterSlot() {
  return Boolean(slots.filters) && !props.deskOnlyFilters;
}
function filterLine() {
  return (
    drawerMode.value &&
    phoneVariant.value &&
    (phoneFilterSlot() ||
      Boolean(slots["filters-primary"] || slots["filters-end"] || slots["filter-panel"]))
  );
}
function deskToolbar() {
  return (
    (!drawerMode.value || deskVariant.value) &&
    Boolean(slots.filters || slots["filters-primary"] || slots["filters-end"] || slots["filter-panel"])
  );
}
const filtersOpen = ref(false);
const activeCount = computed(() => props.activeFilters.length);
// Avisos da tela: um inteiro, o resto em "e mais N".
const alertsOpen = ref(false);
const shownAlerts = computed(() =>
  alertsOpen.value ? props.alerts : props.alerts.slice(0, SCREEN_ALERTS_VISIBLE),
);
const hiddenAlerts = computed(() => Math.max(0, props.alerts.length - SCREEN_ALERTS_VISIBLE));
function alertActions(alert: OperatorScreenAlert) {
  if (!alert.action) return undefined;
  // A saída do aviso repete a cor dele, no tamanho da suíte (`md`), nunca o `xs` do
  // default do aviso.
  return [
    {
      label: alert.action.label,
      to: alert.action.to,
      color: alert.color,
      variant: "outline" as const,
      size: "md" as const,
      onClick: (event: Event) => alert.action?.onSelect?.(event),
    },
  ];
}
function clearAll() {
  if (props.clearFilters) props.clearFilters();
  else for (const filter of [...props.activeFilters]) filter.remove();
}
</script>

<template>
  <NuxtDashboardNavbar
    as="header"
    :toggle="Boolean(suiteRail)"
    class="print:hidden"
    data-operator-page-header
  >
    <template #leading>
      <OperatorAppSeal v-if="hubUrl && !$slots.lead" :class="sealClass" />
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
      <span :class="phoneTitle ? 'max-sm:hidden' : ''">{{ title }}</span>
      <span v-if="phoneTitle" class="sm:hidden" data-page-header-phone-title>{{
        phoneTitle
      }}</span>
      <NuxtBadge
        v-if="eyebrowText"
        color="neutral"
        class="max-sm:hidden"
        data-page-header-eyebrow
        >{{ eyebrowText }}</NuxtBadge
      >
    </template>

    <!-- No celular, o estado e o posto descem para uma segunda linha da barra (o
         `basis-full` quebra a linha do `left`, que no tema é `max-sm:flex-wrap`): ao
         lado do título eles se espremiam por cima dele. -->
    <template v-if="eyebrowText || $slots.subtitle || $slots.status" #trailing>
      <div
        class="flex min-w-0 items-center gap-1.5 max-sm:basis-full max-sm:flex-wrap"
        data-page-header-status
      >
        <NuxtBadge
          v-if="eyebrowText"
          color="neutral"
          class="sm:hidden"
          data-page-header-eyebrow-phone
          >{{ eyebrowText }}</NuxtBadge
        >
        <slot name="subtitle" />
        <slot name="status" />
      </div>
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
        :class="phoneLayout.searchIcon ? '' : 'max-sm:hidden'"
        color="neutral"
        variant="ghost"
        icon="i-lucide-search"
        square
        aria-label="Buscar"
        aria-haspopup="dialog"
        data-page-header-search-toggle
        @click="openSearch"
      />
      <!-- As ações de polegar são do celular (o comentário do topo): do `md` para cima o
           `#actions` já está na linha, e as duas juntas desenham o mesmo gesto duas vezes. -->
      <div
        v-if="$slots['phone-actions']"
        class="flex items-center md:hidden"
        data-page-header-phone-actions
      >
        <slot name="phone-actions" />
      </div>
      <div
        v-if="$slots.actions && !actionsBelow"
        class="flex items-center gap-2"
        :class="actionsClass"
        data-page-header-actions
      >
        <slot name="actions" />
      </div>
      <!-- Celular: as ações da tela que ganharam vaga de ícone. -->
      <NuxtButton
        v-for="action in phoneLayout.icons"
        :key="action.label"
        class="sm:hidden"
        :icon="action.icon"
        :to="action.to"
        :target="action.target"
        :disabled="action.disabled"
        color="neutral"
        variant="ghost"
        square
        :aria-label="action.label"
        :title="action.label"
        data-page-header-icon-action
        @click="action.onSelect?.($event)"
      />
      <!-- O ⋯ "Mais ações": no celular, o que não ganhou vaga; do `sm` para cima, as
           ações declaradas (ao lado do `#actions`). -->
      <OperatorMoreMenu
        v-if="phoneVariant && phoneLayout.overflow.length"
        :items="phoneMenuItems"
        :label="actionsLabel"
        class="sm:hidden"
        data-page-header-more
      />
      <OperatorMoreMenu
        v-if="deskVariant && declaredActions.length"
        :items="deskMenuItems"
        :label="actionsLabel"
        class="max-sm:hidden"
        data-page-header-more
      />
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

  <!-- Toolbar no celular (abaixo de `sm`, no shell): UMA linha de altura fixa, com os
       primários da tela e "Filtros"; o resto mora no painel de baixo. -->
  <template v-if="filterLine()">
    <NuxtDashboardToolbar
      class="py-2 sm:hidden"
      :class="$slots.selection ? 'lg:hidden' : ''"
      data-page-header-filter-line
    >
      <div class="flex w-full min-w-0 flex-nowrap items-center gap-2">
        <div
          v-if="$slots['filters-primary']"
          class="flex min-w-0 flex-1 flex-nowrap items-center gap-2 overflow-x-auto no-scrollbar [&>*]:shrink-0"
          data-page-header-filters-primary
        >
          <slot name="filters-primary" />
        </div>
        <!-- Sem primário, a leitura (`#filters-end`) cabe na linha. -->
        <div
          v-else-if="$slots['filters-end']"
          class="flex min-w-0 flex-1 items-center"
          data-page-header-filters-end
        >
          <slot name="filters-end" />
        </div>
        <!-- O painel de filtros único (fase 2, K4): no celular, só o ícone com o
             número, fixo à direita da linha (o último a sair). -->
        <div
          v-if="$slots['filter-panel']"
          class="ms-auto shrink-0"
          data-page-header-filter-panel
        >
          <slot name="filter-panel" />
        </div>
        <NuxtButton
          v-if="phoneFilterSlot()"
          class="ms-auto shrink-0"
          icon="i-lucide-sliders-horizontal"
          color="neutral"
          variant="outline"
          :title="filtersButtonLabel(activeCount)"
          aria-haspopup="dialog"
          :aria-expanded="filtersOpen"
          :aria-label="filtersButtonLabel(activeCount)"
          data-page-header-filters-open
          @click="filtersOpen = true"
        >
          <!-- Abaixo de 360 px o rótulo sai da vista (fica no nome acessível e no
               `title`): a 320 px ele empurrava o período para trás da rolagem. -->
          <span class="max-[359.98px]:sr-only">Filtros</span>
          <template v-if="activeCount" #trailing>
            <NuxtBadge
              color="primary"
              size="sm"
              :label="String(activeCount)"
              data-page-header-filters-count
            />
          </template>
        </NuxtButton>
      </div>
    </NuxtDashboardToolbar>
    <NuxtDashboardToolbar
      v-if="activeFilters.length"
      class="py-2 sm:hidden"
      data-page-header-active-filters
    >
      <div
        class="flex w-full flex-nowrap items-center gap-2 overflow-x-auto no-scrollbar [&>*]:shrink-0"
      >
        <NuxtButton
          v-for="filter in activeFilters"
          :key="filter.key"
          :label="filter.label"
          trailing-icon="i-lucide-x"
          color="primary"
          variant="ghost"
          active
          active-variant="soft"
          :aria-label="`Tirar o recorte ${filter.label}`"
          data-page-header-active-filter
          @click="filter.remove()"
        />
      </div>
    </NuxtDashboardToolbar>
    <!-- Com primário na linha, a leitura (o frescor) desce para uma faixa de texto
         própria, como o `ReadFreshness` fora do cabeçalho: espremida ao lado do
         período, ela se cortava ("Últim…"). -->
    <div
      v-if="$slots['filters-primary'] && $slots['filters-end']"
      class="border-b border-default bg-card px-4 py-1 sm:hidden [&_[data-read-freshness]]:max-w-none"
      data-page-header-filters-end
    >
      <slot name="filters-end" />
    </div>
    <NuxtDrawer
      v-if="phoneFilterSlot()"
      v-model:open="filtersOpen"
      title="Filtros"
      description="Recortes e controles desta tela."
      direction="bottom"
    >
      <template #body>
        <div
          class="flex flex-col items-stretch gap-4 [&>*]:max-w-full"
          data-page-header-filters-panel
        >
          <slot name="filters" />
        </div>
      </template>
      <template #footer>
        <div class="flex w-full items-center gap-2">
          <NuxtButton
            class="flex-1 justify-center"
            label="Limpar"
            color="neutral"
            variant="outline"
            :disabled="!activeCount"
            data-page-header-filters-clear
            @click="clearAll()"
          />
          <NuxtButton
            class="flex-1 justify-center"
            label="Ver resultados"
            data-page-header-filters-done
            @click="filtersOpen = false"
          />
        </div>
      </template>
    </NuxtDrawer>
  </template>

  <NuxtDashboardToolbar
    v-if="deskToolbar()"
    class="py-2"
    :class="[drawerMode ? 'max-sm:hidden' : '', $slots.selection ? 'lg:hidden' : '']"
  >
    <div
      class="flex w-full items-center gap-2"
      :class="
        filtersWrap
          ? 'flex-wrap'
          : 'flex-nowrap overflow-x-auto no-scrollbar [&>*]:shrink-0'
      "
      data-page-header-filters
    >
      <slot name="filters-primary" />
      <slot name="filter-panel" />
      <slot name="filters" />
      <slot name="filters-end" />
    </div>
  </NuxtDashboardToolbar>

  <!-- A barra de seleção (fase 2, K2): do `lg` para cima ela OCUPA O LUGAR da toolbar
       enquanto houver marcados (dono, 09/10/2026); abaixo, a tela a põe na base
       (`OperatorBulkBar placement="base"`) e a toolbar fica. Por CSS: o servidor e o
       cliente desenham a mesma árvore. -->
  <NuxtDashboardToolbar
    v-if="$slots.selection"
    class="py-2 max-lg:hidden"
    data-page-header-selection
  >
    <slot name="selection" />
  </NuxtDashboardToolbar>

  <!-- Navegação secundária da tela (as abas de Ajustes do PDV, o prazo do anúncio no
       Marketing, a seção do Compras no celular). Vue descarta slot não declarado sem
       aviso: sem esta linha, as abas de Ajustes do PDV somem. -->
  <slot name="below" />

  <!-- O aviso da tela (fase 2, K6): abaixo da toolbar, um inteiro e o resto em "e mais
       N". Lugar declarado: a tela não monta faixa de aviso própria. -->
  <div
    v-if="alerts.length"
    class="flex flex-col gap-2 px-4 py-2 sm:px-6"
    data-page-header-alerts
  >
    <NuxtAlert
      v-for="alert in shownAlerts"
      :key="alert.id ?? alert.title"
      :color="alert.color"
      variant="subtle"
      :icon="alert.icon ?? screenAlertIcon(alert.color)"
      :title="alert.title"
      :description="alert.description"
      :actions="alertActions(alert)"
      orientation="horizontal"
      :role="alert.color === 'error' ? 'alert' : 'status'"
      data-page-header-alert
    />
    <NuxtButton
      v-if="hiddenAlerts && !alertsOpen"
      class="self-start"
      :label="moreAlertsLabel(hiddenAlerts)"
      color="neutral"
      variant="ghost"
      trailing-icon="i-lucide-chevron-down"
      :aria-expanded="false"
      data-page-header-alerts-more
      @click="alertsOpen = true"
    />
  </div>

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
