// PRÉVIA C (compacto) do Gestor de pedidos. Roda numa cópia temporária DEPOIS do
// apply-conn-sim (aplicado igual em A e C). Nunca escreve na árvore do produto.
// Âncoras de string: se o código do main mudar, falha alto.
//
// Réguas: no A convivem três (<sm: barra do kit + linha "Filtros" + painel do kit;
// sm–md: barra do kit + chip "Filtros" que abre o painel próprio da fila; ≥md: a
// linha da mesa). No C as duas de baixo viram UMA (<md, a linha compacta); do md para
// cima nada muda (CSS só abaixo de 768px e a barra é `md:hidden`).
import {readFile,writeFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {join} from 'node:path';
const root=process.argv[2];if(!root)throw Error('Informe a cópia temporária do orders-nuxt.');
execFileSync(process.execPath,[new URL('../compact-kit/apply-kit.mjs',import.meta.url).pathname,join(root,'../operator-kit')],{stdio:'inherit'});
const CENTRAL='https://sim-washing-refers-roberts.trycloudflare.com/';
let s;
function swap(from,to){const n=s.split(from).length-1;if(n!==1)throw Error(`Encaixe ${n===0?'ausente':'repetido'}: `+from.slice(0,70));s=s.replace(from,to);}
const HIDE=`
<style>
/* PRÉVIA C: abaixo do md a linha compacta é o cabeçalho inteiro. Somem a barra de 56px
   do kit e as faixas de filtro dele; ficam o aviso da tela e o sinal do canal. */
@media (max-width: 767.98px) {
  [data-compact-page] [data-operator-page-header],
  [data-compact-page] [data-page-header-filter-line],
  [data-compact-page] [data-page-header-active-filters],
  [data-compact-page] [data-page-header-filters-end],
  [data-compact-page] [data-operator-page-header-landmark] > :has([data-page-header-filters]) { display: none !important; }
}
</style>
`;

// ── Quadro (pages/index.vue) ─────────────────────────────────────────────────
let file=join(root,'app/pages/index.vue');s=await readFile(file,'utf8');
swap('function printQueue() {\n  window.print();\n}\n',`function printQueue() {
  window.print();
}
// PRÉVIA C: variante de Avisos (?avisos=options leva o sino para o ⋮).
const previewAvisos = useState<'own' | 'options'>('preview-avisos', () => (route.query.avisos === 'options' ? 'options' : 'own'));
watch(() => route.query.avisos, (v) => { if (v === 'own' || v === 'options') previewAvisos.value = v; });
// O ⋮ da linha: as MESMAS ações do ⋯ do celular no A (som, atualizar, selecionar,
// exportar, imprimir). Visto e Som bloqueado também ficam aqui, mas NÃO só aqui: eles
// ganham a faixa de atenção logo abaixo (regra 4).
const compactOptions = computed(() => phoneHeaderActions.value.map(({ priority: _p, ...item }) => item));
const compactTotal = computed(() => zones.value.reduce((n, z) => n + z.cards.length, 0));
const compactFilterLabel = computed(() => activeFilters.value.map((f) => f.label).join(', '));
function compactClear() {
  query.value = "";
  channel.value = "all";
  fulfillment.value = "all";
}
`);
swap('<main class="flex min-h-0 flex-1 flex-col">','<main class="flex min-h-0 flex-1 flex-col" data-compact-page>');
swap(`    <OperatorPageHeader
      :title="exitPostView ? 'Saída' : 'Pedidos'"`,`    <OperatorCompactBar
      :title="phoneExitMode ? 'Saída' : 'Pedidos'"
      :tone="liveTone"
      :time="readClock"
      :conn-label="error ? 'Atualização falhou' : realtimeView.label"
      :query="query"
      search-label="Buscar por código, cliente ou item"
      :filter-active="channel !== 'all' || fulfillment !== 'all'"
      :filter-label="compactFilterLabel"
      :summary="visibleCount + ' de ' + compactTotal + ' pedidos no quadro.'"
      :options="compactOptions"
      :avisos="previewAvisos"
      to="${CENTRAL}"
      @clear="compactClear"
    >
      <template v-if="!phoneExitMode" #filters="{ close }">
        <OperatorQuickFilters
          :model-value="fulfillment"
          :items="fulfillmentFilterTabs"
          label="Tipo de entrega"
          data-fulfillment-filters
          @update:model-value="pickFulfillment(String($event))"
        />
        <NuxtFormField v-if="channels.length" label="Canal">
          <NuxtSelect v-model="channel" :items="channelItems" class="w-full" aria-label="Canal" data-channel-picker />
        </NuxtFormField>
        <NuxtFormField label="Ordenar">
          <NuxtDropdownMenu :items="sortMenuItems" :content="{ align: 'start' }">
            <NuxtButton icon="i-lucide-arrow-up-down" trailing-icon="i-lucide-chevron-down" :label="sortLabel" color="neutral" variant="outline" class="min-h-11" data-board-sort />
          </NuxtDropdownMenu>
        </NuxtFormField>
        <NuxtFormField label="Ver como">
          <NuxtTabs :model-value="view" :items="viewTabs" :content="false" variant="pill" aria-label="Visão do Gestor" data-view-switch @update:model-value="pickView" />
        </NuxtFormField>
      </template>
    </OperatorCompactBar>
    <!-- PRÉVIA C: sem conexão segue EXPLÍCITO (cor + texto), não só o chip do selo. Com a
         leitura falhada o conteúdo já diz "Falha ao atualizar a fila"; aqui não repete. -->
    <p v-if="liveTone === 'off' && !error" class="flex items-center gap-2 border-b border-default bg-error/10 px-3 py-2 text-sm text-error md:hidden" role="status" data-compact-offline>
      <NuxtIcon name="i-lucide-wifi-off" class="size-4 shrink-0" /><span>Sem conexão.<template v-if="readClock"> Última leitura às {{ readClock }}.</template></span>
    </p>
    <!-- PRÉVIA C: o que hoje ganha vaga de ícone por ser urgente vira faixa explícita. -->
    <div
      v-if="(attentionPending && !exitPostView) || (soundOn && soundBlocked)"
      class="flex flex-col border-b border-default bg-warning/10 md:hidden"
      role="status"
      data-compact-attention
    >
      <!-- Uma linha só, mesmo com os dois: pedido novo e som bloqueado juntos (o caso de
           toda carga até o 1º gesto) custavam duas linhas, 96px a 320. -->
      <div class="flex items-center gap-2 px-3 py-0.5">
        <NuxtIcon :name="attentionPending && !exitPostView ? 'i-lucide-bell-ring' : 'i-lucide-volume-x'" class="size-4 shrink-0 text-warning" />
        <p class="min-w-0 flex-1 text-sm leading-tight">{{ attentionPending && !exitPostView ? (soundOn && soundBlocked ? 'Pedido novo. Som bloqueado.' : 'Pedido novo chegou.') : 'Som bloqueado: pedido novo não toca.' }}</p>
        <NuxtButton v-if="soundOn && soundBlocked" :icon="attentionPending && !exitPostView ? 'i-lucide-volume-2' : undefined" :label="attentionPending && !exitPostView ? undefined : 'Ativar som'" :square="attentionPending && !exitPostView" color="warning" variant="soft" class="min-h-11 min-w-11 shrink-0 justify-center" aria-label="Som bloqueado pelo navegador: ativar som" data-compact-sound @click="handleSoundAction" />
        <NuxtButton v-if="attentionPending && !exitPostView" icon="i-lucide-check" label="Visto" color="warning" variant="soft" class="min-h-11 shrink-0" aria-label="Visto: parar o som de pedido novo" data-compact-visto @click="acknowledgeAttention" />
      </div>
    </div>
    <OperatorPageHeader
      :title="exitPostView ? 'Saída' : 'Pedidos'"`);
s+=HIDE;
await writeFile(file,s);

// ── Detalhe (pages/[ref].vue): tela de REGISTRO ──────────────────────────────
file=join(root,'app/pages/[ref].vue');s=await readFile(file,'utf8');
swap('<main class="flex min-h-0 flex-1 flex-col">','<main class="flex min-h-0 flex-1 flex-col" data-compact-page>');
swap(`    <OperatorPageHeader
      :title="\`Pedido \${code.code}\`"`,`    <OperatorCompactBar :title="\`Pedido \${code.code}\`" search-label="Buscar na suíte">
      <template #lead>
        <NuxtButton :to="backLocation" icon="i-lucide-arrow-left" color="neutral" variant="ghost" square class="size-11 shrink-0 justify-center"
          :aria-label="fromHistory ? 'Voltar para o histórico' : 'Voltar para a fila'" data-compact-back />
      </template>
      <template #identity>
        <div class="flex min-w-0 items-center gap-1" data-compact-record>
          <div class="min-w-0 flex-1">
            <p class="flex min-w-0 items-center gap-1.5">
              <span class="truncate text-lg font-semibold leading-tight text-highlighted">{{ code.code }}</span>
              <NuxtBadge v-if="order?.status_label" size="sm" :color="statusColor(order.status)" :label="order.status_label" class="shrink-0" />
            </p>
            <p v-if="order" class="flex min-w-0 items-center gap-1 text-xs text-muted">
              <Icon :name="channelIcon" class="size-3.5 shrink-0" /><span class="truncate">{{ order.channel_name || order.channel_ref }}</span>
            </p>
          </div>
          <OperatorRecordNav v-if="!returnTicket" :trail="recordTrailKey" :current="orderRef" :to="recordLocation" previous-label="Pedido anterior" next-label="Próximo pedido" />
          <NuxtButton icon="i-lucide-ellipsis" color="neutral" variant="ghost" square class="size-11 shrink-0 justify-center"
            aria-label="Mais ações do pedido" :aria-expanded="menuOpen" data-action="menu-phone" @click="menuOpen = !menuOpen" />
        </div>
      </template>
    </OperatorCompactBar>
    <OperatorPageHeader
      :title="\`Pedido \${code.code}\`"`);
s+=HIDE;
await writeFile(file,s);
console.log('apply-compact: quadro e detalhe aplicados');
