// PRÉVIA C (compacto) do PDV. Roda numa CÓPIA temporária de origin/main
// (surfaces/pos-nuxt + surfaces/operator-kit). Nunca escreve na árvore do produto.
// Só o cabeçalho do celular (< md) muda: Comandas, Venda, Checkout, a barra da venda
// (PosTabHeader no #below), os avisos da tela, o OperatorActionBar e o checkout ficam
// como estão. Cada encaixe é uma âncora de texto: se o main mudar, FALHA alto.
import {readFile,writeFile,copyFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {join} from 'node:path';
const root=process.argv[2];if(!root)throw Error('Informe surfaces/pos-nuxt da cópia temporária.');
execFileSync(process.execPath,[new URL('../compact-kit/apply-kit.mjs',import.meta.url).pathname,join(root,'../operator-kit')],{stdio:'inherit'});
const CENTRAL='https://sim-washing-refers-roberts.trycloudflare.com/';
async function patch(rel,fn){const file=join(root,rel);let s=await readFile(file,'utf8');
  const swap=(from,to)=>{if(!s.includes(from))throw Error(`Encaixe ausente em ${rel}: ${from.slice(0,70)}`);s=s.replace(from,to);};
  fn(swap);await writeFile(file,s);}
// Sem conexão o PDV não tem "ao vivo" (posLiveStatus devolve null): o chip mostra ×,
// além da faixa do OfflineBanner que já existe.
const LIVE=`:tone="liveStatus.view.value?.tone ?? 'off'" :time="liveStatus.time.value" :conn-label="liveStatus.view.value?.label ?? 'Sem conexão'"`;

// 0. CSS do compacto + abas roláveis de Ajustes (da prévia anterior, ver o arquivo).
await copyFile(new URL('compact.css',import.meta.url),join(root,'app/assets/css/compact-preview.css'));
await copyFile(new URL('PosSettingsTabs.vue',import.meta.url),join(root,'app/components/PosSettingsTabs.vue'));
await patch('nuxt.config.ts',(swap)=>swap('css: ["~/assets/css/tailwind.css"]','css: ["~/assets/css/tailwind.css", "~/assets/css/compact-preview.css"]'));

// 1. Comandas, Venda e Checkout (pages/index.vue): só a linha do topo do celular.
//    Selos "Não salvo" e PIX ficam VISÍVEIS na linha (regra 4), nunca no ⋮.
await patch('app/pages/index.vue',(swap)=>{
  swap('// A VENDA SEM CONEXÃO: a fila de vendas guardadas',
`// PRÉVIA C: as mesmas ações do ⋯ do cabeçalho, no ⋮ da linha compacta.
// O ⋮ compacto (NuxtDropdownMenu) não escreve o \`reason\` sob a ação desabilitada como o
// OperatorMoreMenu faz: aqui ele vira uma linha de texto logo abaixo.
const compactOptions = computed(() => headerActions.value.flatMap(({ priority: _p, reason, ...action }) =>
  action.disabled && reason ? [action, { label: reason, type: "label" }] : [action]));
// A VENDA SEM CONEXÃO: a fila de vendas guardadas`);
  swap('<main class="flex min-h-0 flex-1 flex-col" data-pos-sale-screen>','<main class="flex min-h-0 flex-1 flex-col" data-pos-sale-screen data-compact-page>');
  swap(`      <OperatorPageHeader
        v-if="pos"
        :title="saleHeaderTitle"`,
`      <OperatorCompactBar v-if="pos" :title="saleHeaderTitle" ${LIVE}
        search-label="Buscar pedido, cliente, produto ou tela" :options="compactOptions" to="${CENTRAL}">
        <template v-if="inSaleView && !editing && !result" #lead>
          <NuxtButton color="neutral" variant="ghost" icon="i-lucide-arrow-left" square class="size-11 shrink-0 justify-center"
            :aria-label="checkoutMode ? 'Voltar à comanda' : 'Voltar para comandas'" data-compact-back
            @click="checkoutMode ? (checkoutMode = false) : goToTabs()" />
        </template>
        <template v-if="inSaleView || editing || result || pixBadge" #identity>
          <div class="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 leading-tight" data-compact-identity-sale>
            <span v-if="inSaleView || editing || result" class="min-w-0 truncate font-semibold"
              :class="(inSaleView && !checkoutMode && unsaved) || pixBadge ? 'sr-only' : ''">{{ checkoutMode ? 'Pagamento' : saleHeaderTitle }}</span>
            <NuxtBadge v-if="inSaleView && !checkoutMode && unsaved" color="warning" icon="i-lucide-cloud-off" label="Não salvo" role="status"
              :title="tabConflict ? 'A comanda mudou em outro dispositivo. Confira antes de salvar.' : 'A comanda não foi salva. Tentando de novo.'" data-compact-unsaved />
            <NuxtBadge v-if="pixBadge" color="info" icon="i-lucide-loader-circle" role="status" :title="pixBadge.title" class="whitespace-normal" data-compact-pix>{{ pixBadge.label }}</NuxtBadge>
          </div>
        </template>
      </OperatorCompactBar>
      <OperatorPageHeader
        v-if="pos"
        :title="saleHeaderTitle"`);
});

// 2. Encomendas e o detalhe: a moldura comum ganha a linha compacta, com o que cada
//    tela passa (recortes no painel de filtros, identidade e voltar no detalhe).
await patch('app/components/PosPreordersShell.vue',(swap)=>{
  swap('  title?: string;\n}>(), {',
`  title?: string;
  /** PRÉVIA C: a linha compacta do celular. */
  compactQuery?: string;
  compactFilterActive?: boolean;
  compactFilterLabel?: string;
  compactSummary?: string;
  compactOptions?: any[][];
}>(), {
  compactQuery: "",
  compactFilterActive: false,
  compactFilterLabel: "",
  compactSummary: "",
  compactOptions: () => [],`);
  swap('const emit = defineEmits<{ refresh: [] }>();',`const emit = defineEmits<{ refresh: []; "compact-clear": [] }>();
const liveStatus = usePosLiveStatus();
// O ⋮ compacto não escreve o \`reason\` da ação desabilitada (o OperatorMoreMenu escreve).
const compactGroups = computed(() => [...props.compactOptions, [refreshAction]].map((group) =>
  group.flatMap((item: any) => (item.disabled && item.reason ? [item, { label: item.reason, type: "label" }] : [item]))));`);
  swap('<main class="flex min-h-0 flex-1 flex-col" data-preorders-shell>',
`<main class="flex min-h-0 flex-1 flex-col" data-preorders-shell data-compact-page>
    <OperatorCompactBar :title="title" ${LIVE} :query="compactQuery"
      search-label="Buscar encomenda: código, nome ou telefone" :filter-active="compactFilterActive" :filter-label="compactFilterLabel"
      :summary="compactSummary" :options="compactGroups" to="${CENTRAL}" @clear="emit('compact-clear')">
      <template v-if="$slots['compact-lead']" #lead><slot name="compact-lead" /></template>
      <template v-if="$slots['compact-identity']" #identity><slot name="compact-identity" /></template>
      <template v-if="$slots['compact-filters']" #filters="scope"><slot name="compact-filters" v-bind="scope" /></template>
    </OperatorCompactBar>`);
});

await patch('app/pages/preorders/index.vue',(swap)=>{
  swap('import type { PeriodSelection } from "../../../../operator-kit/app/presentation/dates";',
`import type { PeriodSelection } from "../../../../operator-kit/app/presentation/dates";
import { periodLabel as compactPeriodLabel, resolvePeriod as compactResolvePeriod } from "../../../../operator-kit/app/presentation/dates";`);
  swap('function refreshAll() {',
`// ── PRÉVIA C: a linha compacta do celular ──
const compactPhone = useScreen().belowMd;
const compactPeriodOff = computed(() => !periodIsToday(view.value, today.value));
const compactFilterActive = computed(() => !searching.value && (compactPeriodOff.value || activeFilters.value.length > 0));
const compactFilterLabel = computed(() => [
  compactPeriodOff.value ? "Período: " + compactPeriodLabel(periodSelection.value, compactResolvePeriod(periodSelection.value, { today: today.value }), today.value) : "",
  ...activeFilters.value.map((filter) => filter.label),
].filter(Boolean).join(" · "));
const compactSummary = computed(() => {
  if (searching.value) return resultCount.value == null ? "" : resultCount.value === 1 ? "1 encontrada." : resultCount.value + " encontradas.";
  return shownCount.value === 1 ? "1 encomenda na tela." : shownCount.value + " encomendas na tela.";
});
const compactNew = { label: "Nova encomenda", icon: "i-lucide-plus", onSelect: () => navigateTo(NEW_ORDER_ROUTE) };
const compactOptions = computed(() => [
  ...(todayLine.value.length ? [[{ label: "Hoje: " + todayLine.value.map((fact) => fact.text).join(", ") + ".", icon: "i-lucide-calendar-check", type: "label" }]] : []),
  [compactNew, ...deskActions.value],
]);
function compactClear() {
  // Limpar = sem busca, sem recortes e de volta ao dia de hoje (a chegada da tela).
  typed.value = "";
  update({ ...fromActiveFilters({}), q: "", mode: "day", date: today.value, to: "" });
}

function refreshAll() {`);
  swap('    :active-filters="searching ? [] : activeFilters"\n    @refresh="refreshAll"\n  >',
`    :active-filters="searching ? [] : activeFilters"
    :compact-query="typed"
    :compact-filter-active="compactFilterActive"
    :compact-filter-label="compactFilterLabel"
    :compact-summary="compactSummary"
    :compact-options="compactOptions"
    @refresh="refreshAll"
    @compact-clear="compactClear"
  >
    <!-- PRÉVIA C: o recorte inteiro (período, recortes, painel) no painel de Filtros. -->
    <template #compact-filters>
      <p v-if="todayLine.length" class="flex flex-wrap items-baseline gap-x-3 text-sm" data-compact-today>
        <span class="font-semibold text-primary">Hoje</span>
        <span v-for="fact in todayLine" :key="fact.key" class="tabular-nums" :class="fact.urgent ? 'font-semibold text-warning' : 'text-muted'">{{ fact.text }}</span>
      </p>
      <template v-if="!searching">
        <OperatorPeriodPicker v-model="periodSelection" :presets="PREORDERS_PERIOD_PRESETS" custom :max-span-days="PREORDERS_MAX_SPAN_DAYS"
          :today="today" label="Período das encomendas" data-compact-period />
        <OperatorQuickFilters v-if="list && list.count" v-model="quickModel" :items="quickItems" multiple label="Recortes"
          surface="pos" screen="preorders" :query="panelQuery" data-compact-quick @apply="applyFavorite" />
        <OperatorFilterPanel v-if="list && list.count" v-model="activePanel" :dimensions="dimensions" surface="pos" screen="preorders" data-compact-panel />
        <div v-if="activeFilters.length" class="flex flex-wrap gap-2" data-compact-chips>
          <NuxtButton v-for="filter in activeFilters" :key="filter.key" :label="filter.label" trailing-icon="i-lucide-x" color="primary"
            variant="soft" class="min-h-11" :aria-label="'Tirar o recorte ' + filter.label" @click="filter.remove()" />
        </div>
      </template>
      <NuxtSwitch v-else v-model="includeCompleted" label="Incluir concluídas" />
    </template>`);
  // "Nova encomenda" vai para o lugar da tarefa: a segunda ação da barra de baixo que
  // já existe (e o ⋮). Do md para cima, a barra de baixo fica como está.
  swap(`        :action="{ label: 'Ler código da encomenda', icon: 'i-lucide-scan-qr-code', onSelect: () => { scannerOpen = true; } }"`,
`        :action="{ label: 'Ler código da encomenda', shortLabel: 'Ler código', icon: 'i-lucide-scan-qr-code', onSelect: () => { scannerOpen = true; } }"
        :secondary="compactPhone ? { label: 'Nova encomenda', shortLabel: 'Nova', icon: 'i-lucide-plus', onSelect: () => navigateTo(NEW_ORDER_ROUTE) } : undefined"`);
});

await patch('app/pages/preorders/[ref].vue',(swap)=>{
  swap(':title="`Encomenda ${ref_}`" wide @refresh="refreshPos(); refresh()">',
`:title="\`Encomenda \${ref_}\`" wide @refresh="refreshPos(); refresh()">
    <!-- PRÉVIA C: voltar e a identidade do registro na linha compacta. -->
    <template #compact-lead>
      <NuxtButton color="neutral" variant="ghost" icon="i-lucide-arrow-left" square class="size-11 shrink-0 justify-center"
        aria-label="Voltar às encomendas" data-compact-back @click="goBack" />
    </template>
    <template #compact-identity>
      <p class="min-w-0 leading-tight" data-compact-identity-preorder>
        <span class="block text-xs text-muted">Encomenda</span>
        <span class="block break-all font-semibold">{{ ref_ }}</span>
      </p>
    </template>`);
  swap('          data-preorder-back\n','          data-preorder-back\n          data-compact-desk-back\n');
});

// 3. Caixa: "Terminal · operador" sai da toolbar só de texto e vai ao topo das Opções.
await patch('app/pages/session/index.vue',(swap)=>{
  swap('<main class="flex min-h-0 flex-1 flex-col" data-session-screen>','<main class="flex min-h-0 flex-1 flex-col" data-session-screen data-compact-page>');
  swap('      <OperatorPageHeader title="Sessão de caixa"',
`      <OperatorCompactBar title="Sessão de caixa" ${LIVE} to="${CENTRAL}"
        :options="[[{ label: (pos?.terminal_label || 'Terminal') + (screen === 'open' ? ' · ' + (activeOperator?.name || cashRuntime?.operator_username || '') : ''), icon: 'i-lucide-monitor', type: 'label' }], headerActions]" />
      <OperatorPageHeader title="Sessão de caixa"`);
});

// 4. Ajustes: sem título repetido; as abas roláveis logo abaixo da linha.
await patch('app/components/PosSettingsShell.vue',(swap)=>{
  swap('<main class="flex min-h-0 flex-1 flex-col" data-pos-settings-shell>',
`<main class="flex min-h-0 flex-1 flex-col" data-pos-settings-shell data-compact-page>
    <OperatorCompactBar :title="'Ajustes, ' + title" ${LIVE} to="${CENTRAL}" :options="headerActions" />
    <div class="border-b border-default md:hidden" data-compact-settings-tabs><PosSettingsTabs /></div>`);
  swap('const { pos, refresh: refreshPos } = await usePosTerminal();','const { pos, refresh: refreshPos } = await usePosTerminal();\nconst liveStatus = usePosLiveStatus();');
});
await patch('app/pages/settings/seating.vue',(swap)=>{
  swap('<main class="flex min-h-0 flex-1 flex-col" data-seating-screen>',
`<main class="flex min-h-0 flex-1 flex-col" data-seating-screen data-compact-page>
    <OperatorCompactBar title="Ajustes, Salão" ${LIVE} to="${CENTRAL}" :options="headerActions" />
    <div class="border-b border-default md:hidden" data-compact-settings-tabs><PosSettingsTabs /></div>`);
  swap('const screen = useScreen();','const screen = useScreen();\nconst liveStatus = usePosLiveStatus();');
});
console.log('PRÉVIA C aplicada em',root);
