<script setup lang="ts">
// A moldura das Encomendas dentro do shell da suíte (fase 2): o cabeçalho de uma
// linha do kit (`OperatorPageHeader`), a área de conteúdo que rola e, no pé, a ação
// do momento no celular (`OperatorActionBar`, slot `footer`). A navegação (barra
// lateral, gaveta, barra inferior) é do shell, montada uma vez em `PosOperatorShell`.
// A tela da seção e o detalhe dividem esta peça em vez de repetir o cabeçalho — o
// guardrail do cabeçalho (`guardrails.appBar.test.ts`) não deixa cabeçalho novo
// nascer à mão.
//
// Os papéis das barras (WP-FASE2-UX-OPERADOR, seção 5), sem barra própria:
// - barra primária: o título, a busca (`#search`: na seção é o "Cliente veio
//   buscar", com o `/`), a ação primária da tela (`#primary`, só na mesa) e o ⋯
//   "Mais ações" (`actions`, com "Atualizar" sempre no fim; `phone-actions` no
//   celular, onde a ação primária entra no topo do ⋯);
// - toolbar: o modo da tela (`#filters-primary`: o período), o filtro único da suíte
//   (`#filter-panel`, dono 04/11/2026), `#filters` só na mesa e a leitura em
//   `#filters-end`, com os recortes ativos (`active-filters`);
// - no celular, a linha do chão: o filtro único no ícone da linha
//   (`#compact-filter-panel`) e o modo da tela numa faixa logo abaixo
//   (`#compact-primary`);
// - aviso da tela (`alerts`);
// - a PORTA da seção é o item "Encomendas" da barra lateral (decisão do dono,
//   26/09): o nome no começo da barra é só o título, não é segundo link.
import type { OperatorActiveFilter, OperatorHeaderAction } from "../../../operator-kit/app/presentation/pageHeader";
import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";
import type { POSProjection } from "~/types/pos";

const props = withDefaults(defineProps<{
  pos: POSProjection | null;
  pending: boolean;
  /** Largura do conteúdo: a grade semanal precisa da tela inteira. */
  wide?: boolean;
  /** As ações da tela no ⋯ (na mesa); "Atualizar" entra sempre no fim. */
  actions?: OperatorHeaderAction[];
  /** As ações do ⋯ no celular, quando diferem das da mesa; "Atualizar" no fim. */
  phoneActions?: OperatorHeaderAction[];
  alerts?: OperatorScreenAlert[];
  activeFilters?: OperatorActiveFilter[];
  /** O título do cabeçalho; o detalhe diz qual encomenda ("Encomenda PDV-…"). */
  title?: string;
  /**
   * A linha do chão no celular (modelo de navegação, 31/10/2026): o termo buscado, o
   * recorte ativo (nomeado) e a contagem, sempre à vista; e as ações do ⋮ dela.
   */
  compactQuery?: string;
  compactFilterActive?: boolean;
  compactFilterLabel?: string;
  compactSummary?: string;
  compactOptions?: OperatorHeaderAction[];
}>(), {
  compactQuery: "",
  compactFilterActive: false,
  compactFilterLabel: "",
  compactSummary: "",
  compactOptions: undefined,
  title: "Encomendas",
  wide: false,
  actions: () => [],
  phoneActions: undefined,
  alerts: () => [],
  activeFilters: () => [],
});

const emit = defineEmits<{ refresh: []; "compact-clear": [] }>();
const screen = useScreen();

const refreshAction: OperatorHeaderAction = {
  label: "Atualizar",
  icon: "i-lucide-refresh-cw",
  onSelect: () => emit("refresh"),
};
const headerActions = computed<OperatorHeaderAction[]>(() => [...props.actions, refreshAction]);
// O ⋮ da linha do chão: as ações dela (ou as da mesa) e Atualizar no fim.
const compactGroups = computed(() =>
  [...(props.compactOptions ?? props.actions), refreshAction].map(({ priority: _p, ...action }) => action),
);
const headerPhoneActions = computed<OperatorHeaderAction[] | undefined>(() =>
  props.phoneActions ? [...props.phoneActions, refreshAction] : undefined,
);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-preorders-shell data-compact-page>
    <!-- No celular, o cabeçalho inteiro numa linha: o selo troca de seção (ou, no
         detalhe, o voltar e a encomenda aberta), a busca, o ⋮ e os avisos. -->
    <PosCompactBar
      :title="title"
      :query="compactQuery"
      search-button-label="Buscar encomenda: nome, telefone, CPF, endereço ou número"
      :filter-active="compactFilterActive"
      :filter-label="compactFilterLabel"
      :summary="compactSummary"
      :options="compactGroups"
      @clear="emit('compact-clear')"
    >
      <template v-if="$slots['compact-lead']" #lead><slot name="compact-lead" /></template>
      <template v-if="$slots['compact-identity']" #identity><slot name="compact-identity" /></template>
      <template v-if="$slots['compact-filter-panel']" #filter-panel><slot name="compact-filter-panel" /></template>
    </PosCompactBar>
    <!-- O modo da tela no celular (o período, ou "Incluir concluídas" na busca), logo
         abaixo da linha: é o que diz de quando é a lista, e trocar não pode custar ⋮. -->
    <div
      v-if="$slots['compact-primary']"
      class="flex min-h-12 items-center gap-2 border-b border-default bg-card px-2 py-1.5 md:hidden"
      data-compact-primary
    >
      <slot name="compact-primary" />
    </div>
    <slot name="compact-below" />
    <OperatorPageHeader
      :title="title"
      :actions="headerActions"
      :phone-actions="headerPhoneActions"
      actions-label="Mais ações das Encomendas"
      :alerts="alerts"
      :active-filters="activeFilters"
      :desk-only-filters="true"
    >
      <!-- Sem `#search` próprio, a busca da suíte fica no Ctrl K e na lupa do celular
           (o `/` é do campo da tela que o tem). -->
      <template #search>
        <slot name="search">
          <OperatorSuiteSearch variant="hotkey" placeholder="Buscar pedido, cliente, produto ou tela" />
        </slot>
      </template>
      <!-- No celular a ação primária é a segunda da base ("Nova" | "Ler código") e o
           primeiro item do ⋮: a faixa dela abaixo da linha do chão seria repetição. -->
      <template v-if="$slots.primary && !screen.belowMd.value" #actions>
        <div class="flex min-w-0 items-center gap-2" data-preorders-actions>
          <slot name="primary" />
        </div>
      </template>
      <template v-if="$slots['filters-primary']" #filters-primary>
        <slot name="filters-primary" />
      </template>
      <template v-if="$slots['filter-panel']" #filter-panel>
        <slot name="filter-panel" />
      </template>
      <template v-if="$slots.filters" #filters>
        <slot name="filters" />
      </template>
      <template v-if="$slots['filters-end']" #filters-end>
        <slot name="filters-end" />
      </template>
    </OperatorPageHeader>

    <div class="relative min-h-0 flex-1 overflow-y-auto">
      <div class="mx-auto grid w-full gap-4 p-4 md:py-6" :class="wide ? 'max-w-screen-2xl' : 'max-w-3xl'">
        <slot />
        <!-- A dica mede o que flutua na base ao montar: quando a ação na base chega
             depois (o detalhe carregou), ela remonta e mede de novo. -->
        <MoreBelow :key="$slots.footer ? 'with-footer' : 'no-footer'" />
      </div>
    </div>

    <!-- A ação do momento no celular: em fluxo, entre o conteúdo e a barra inferior. -->
    <slot name="footer" />
  </main>
</template>
