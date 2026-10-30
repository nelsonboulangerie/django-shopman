// PRÉVIA C (compacto). Roda numa cópia temporária DEPOIS dos três aplicadores da prévia
// anterior (apply-preview, apply-navigation, apply-refinement) e do apply-conn-sim.
// Nunca escreve na árvore do produto.
import {readFile,writeFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {join} from 'node:path';
const root=process.argv[2];if(!root)throw Error('Informe a cópia temporária do KDS.');
// As peças compartilhadas do compacto (selo com chip, linha única, avisos em uma linha).
execFileSync(process.execPath,[new URL('../compact-kit/apply-kit.mjs',import.meta.url).pathname,join(root,'../operator-kit')],{stdio:'inherit'});
const file=join(root,'app/pages/[ref].vue');let s=await readFile(file,'utf8');
function swap(from,to){if(!s.includes(from))throw Error('Encaixe ausente: '+from.slice(0,60));s=s.replace(from,to);}
// 1. A busca/filtro/opções da mesa ficam na linha principal (o "header" da prévia anterior).
swap("const toolsInHeader = computed(() => previewToolsPosition.value === 'header');",
`const toolsInHeader = computed(() => true);
const previewAvisos = useState<'own' | 'options'>('preview-avisos', () => (route.query.avisos === 'options' ? 'options' : 'own'));
watch(() => route.query.avisos, (v) => { if (v === 'own' || v === 'options') previewAvisos.value = v; });
const previewAlertDense = useState<boolean>('preview-alert-dense', () => route.query.aviso === 'denso');
watch(() => route.query.aviso, (v) => { if (v === 'denso' || v === 'normal') previewAlertDense.value = v === 'denso'; });`);
// 2. Sem seletor de estação no título: a estação é a vaga ativa da lateral e da barra inferior.
s=s.replace(/<template #title><KdsPreviewStationMenu[^>]*\/><\/template>/,'<template #title><span data-compact-title>{{ stationTitle }}</span></template>');
// 3. Celular: a linha compacta substitui a barra de 56px, a régua de ferramentas e o resumo.
swap('<main class="flex min-h-0 flex-1 flex-col">','<main class="flex min-h-0 flex-1 flex-col" data-compact-page :data-alert-dense="previewAlertDense || undefined">');
swap('    <OperatorPageHeader\n      data-preview-refined-header',`    <OperatorCompactBar :title="'Cozinha, estação ' + stationTitle" :tone="liveTone" :time="lastRead" :conn-label="liveLabel"
      :query="query" search-label="Buscar pedido por código, cliente ou item" :filter-active="filter !== 'all'"
      :filter-label="filterTabs.find((i) => i.key === filter)?.label" :summary="filteredCards.length + ' de ' + tickets.length + ' na estação'"
      :options="previewToolsActions" :avisos="previewAvisos" to="/preview/central" @clear="clearSearchAndFilter">
      <template #filters="{ close }">
        <p class="text-sm text-muted">Mudanças e cancelamentos que pedem ciência continuam sempre na fila.</p>
        <NuxtButton v-for="item in filterTabs" :key="item.key" :label="item.label + ' · ' + item.count" :icon="filter === item.key ? 'i-lucide-check' : item.icon"
          color="neutral" :variant="filter === item.key ? 'soft' : 'ghost'" class="min-h-11 justify-start" @click="filterModel = item.key; close()" />
      </template>
    </OperatorCompactBar>
    <OperatorPageHeader
      data-preview-refined-header`);
await writeFile(file,s);
const css=join(root,'app/assets/css/preview-composition.css');
// Fila do celular: código, posição e tempo na 1ª linha e o resumo inteiro na 2ª, em TODO
// celular (na prévia anterior só abaixo de 375px; a 390px o resumo quebrava em 3 linhas).
const queueCss=(await readFile(css,'utf8')).replace('@media(max-width:374px) {','@media(max-width:767px) {');
if(!queueCss.includes('@media(max-width:767px) {\n  [data-kds-app] [data-kds-queue-row]'))throw Error('Revisar a regra da fila da prévia anterior.');
await writeFile(css,queueCss+`
/* PRÉVIA C: no celular, a linha compacta é o cabeçalho inteiro; avisos e erros seguem abaixo. */
@media (max-width: 767.98px) {
  [data-compact-page] [data-operator-page-header],
  [data-compact-page] [data-preview-tools-header],
  [data-compact-page] [data-preview-tools-body],
  [data-compact-page] [data-preview-persistent-filter] { display: none !important; }
}
/* VARIANTE ?aviso=denso: o aviso da tela numa linha (texto, ação, fechar). A descrição
   continua no DOM para o leitor de tela; a cor e o ícone do aviso não mudam. */
@media (max-width: 767.98px) {
  [data-compact-page][data-alert-dense] [data-page-header-alerts] { padding-block: 6px; }
  [data-compact-page][data-alert-dense] [data-page-header-alert] { padding-block: 6px; align-items: center; }
  [data-compact-page][data-alert-dense] [data-page-header-alert] > [data-slot=wrapper] { flex-direction: row; align-items: center; gap: 8px; padding-inline-end: 40px; }
  [data-compact-page][data-alert-dense] [data-page-header-alert] [data-slot=title] { flex: 1; min-width: 0; padding-inline-end: 0; }
  [data-compact-page][data-alert-dense] [data-page-header-alert] [data-slot=description] { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; margin: 0; }
  [data-compact-page][data-alert-dense] [data-page-header-alert] > [data-slot=wrapper] > [data-slot=actions] { flex-basis: auto; flex-direction: row; margin-top: 0; }
  [data-compact-page][data-alert-dense] [data-page-header-alert] > [data-slot=wrapper] > [data-slot=actions] button { min-height: 44px; padding-inline: 14px; }
  [data-compact-page][data-alert-dense] [data-page-header-alert] > [data-slot=actions]:has(> [data-slot=close]) { inset-block-start: 50%; transform: translateY(-50%); }
}
`);
