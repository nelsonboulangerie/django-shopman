// Somente sobre a cópia temporária, após apply-preview e apply-navigation.
import {readFile,writeFile,copyFile} from 'node:fs/promises';
import {join} from 'node:path';
const root=process.argv[2];if(!root)throw Error('Informe o runtime temporário.');
await copyFile(new URL('navigation/KdsPreviewTools.vue',import.meta.url),join(root,'app/components/KdsPreviewTools.vue'));
const header=join(root,'../operator-kit/app/components/OperatorPageHeader.vue');let h=await readFile(header,'utf8');
h=h.replace('<template v-if="$slots.search || search" #default>','<template v-if="$slots.search || search" #default><slot name="header-tools"/>');await writeFile(header,h);
const file=join(root,'app/pages/[ref].vue');let s=await readFile(file,'utf8');
const marker='const headerActions = computed<OperatorHeaderAction[]>(() => {';
s=s.replace(marker,`const previewToolsPosition = useState<string>('preview-kds-tools-position', () => String(route.query.tools || 'body'));
watch(() => route.query.tools, value => { if(value==='header'||value==='body') previewToolsPosition.value=value; }, {immediate:true});
const toolsInHeader = computed(() => previewToolsPosition.value === 'header');
const previewToolsVisible = ref(true);
const previewToolsBody = ref<HTMLElement | null>(null);
let previewToolsObserver: IntersectionObserver | undefined;
watch(previewToolsBody, el => {
  previewToolsObserver?.disconnect();
  if (el && import.meta.client) {
    previewToolsObserver = new IntersectionObserver(entries => { previewToolsVisible.value = entries[0]?.isIntersecting ?? true; }, {root:el.parentElement});
    previewToolsObserver.observe(el);
  }
}, {flush:'post'});
onBeforeUnmount(() => previewToolsObserver?.disconnect());
const previewWriteError = useState<string>('preview-kds-write-error', () => '');
const previewPending = computed(() => view.value?.finishingPks.size || 0);
const previewPendingCodes = computed(() => tickets.value.filter(card => view.value?.finishingPks.has(card.pk)).map(card => splitRef(card.order_ref).code).join(', '));
const previewToolsActions = computed(() => [...headerActions.value.filter(a => !a.label.startsWith('Ajustes da estação')), {label:'Som e tamanho do ticket',icon:'i-lucide-settings-2',onSelect:()=>{settingsOpen.value=true;}}]);
${marker}`);
// A régua nova oferece filtros opcionais no celular; não os apaga ao redimensionar.
s=s.replace('watch(isPhone, (phone) => {\n  if (phone) filter.value = "all";\n});','');
s=s.replace('<OperatorPageHeader\n', '<OperatorPageHeader\n      data-preview-refined-header\n');
s=s.replace(':title="stationTitle" :actions="headerActions"',':title="stationTitle" :actions="[]"');
s=s.replace('<template #status>','<template #status>\n        <div v-if="!toolsInHeader && !previewToolsVisible && (query || filter!==\'all\')" class="flex w-full items-center gap-1" data-preview-persistent-filter><span class="min-w-0 flex-1 break-words text-xs">{{query ? `Busca: ${query}` : filterTabs.find(i=>i.key===filter)?.label}} · {{filteredCards.length}} exibidos</span><NuxtButton label="Limpar" variant="ghost" color="neutral" class="min-h-11" @click="clearSearchAndFilter"/></div>');
const tools=`<KdsPreviewTools :query="query" :filter="filter" :filters="filterTabs" :actions="previewToolsActions" :shown="filteredCards.length" :total="tickets.length" @filter="filterModel=$event" @clear="clearSearchAndFilter"/>`;
s=s.replace('      <template #status>',`      <template #header-tools><div v-if="toolsInHeader" class="hidden lg:block w-full min-w-40" data-preview-tools-inline>${tools}</div></template>\n      <template #below><div v-if="toolsInHeader" class="px-3 py-2 lg:hidden" data-preview-tools-header>${tools}</div></template>\n      <template #status>`);
// Busca original segue montada com o mesmo contrato; só o acionador é conjugado.
s=s.replace('    </OperatorPageHeader>',`    </OperatorPageHeader>
    <div v-if="previewWriteError" class="px-3 py-2" data-preview-write-error><NuxtAlert color="error" variant="subtle" title="Ação não concluída" :description="previewWriteError" :close="{variant:'ghost',color:'neutral',class:'size-11'}" @update:open="previewWriteError=''" /></div>
    <div v-if="previewPending" class="px-3 pb-1 text-sm text-warning" role="status" data-preview-pending>Pronto pendente: {{previewPendingCodes}}. Ao sair, a confirmação será enviada e o Desfazer termina.</div>`);
const allDay='        <!-- A FAZER:';
s=s.replace(allDay,`        <div v-if="!toolsInHeader" ref="previewToolsBody" class="pb-1" data-preview-tools-body>${tools}</div>\n${allDay}`);
// A urgência fora do foco continua perceptível, sem tirar o operador do pedido atual.
s=s.replace(':class="rowAlarm(card) ? \'border-2 border-error bg-error/8\' : rowLocked(card)',':class="rowAlarm(card) ? \'border-2 border-error bg-error/8\' : rowLocked(card)'); // componente tratado abaixo
await writeFile(file,s);
const queue=join(root,'app/components/KdsPhoneQueue.vue');s=await readFile(queue,'utf8');s=s.replace('        data-kds-queue-row','        :data-preview-late="card.timer_class === \'timer-late\' || undefined"\n        data-kds-queue-row');
s=s.replace('{{ ticketClockLabel(card) }}','<span v-if="card.timer_class === \'timer-late\'" class="text-xs">Atrasado </span>{{ ticketClockLabel(card) }}');await writeFile(queue,s);
const modal=join(root,'app/components/KdsTicketModal.vue');s=await readFile(modal,'utf8');s=s.replace('<div class="flex items-start justify-between gap-3 p-5">','<div class="flex items-start justify-between gap-3 p-5" data-preview-detail-header>');s=s.replace('<div class="min-w-0">','<div class="min-w-0" data-preview-detail-identity>');s=s.replace('{{ ref_.prefix }}{{ ticket.created_at_display }}', "{{ ref_.prefix.replace(/-$/, '') }} · {{ ticket.created_at_display }}");s=s.replace('<span class="tabular-nums"','<span class="tabular-nums break-words" data-preview-detail-ref');s=s.replace('class="mt-1.5 truncate text-sm font-medium text-foreground/80"','class="mt-1.5 break-words text-sm font-medium text-foreground/80"');await writeFile(modal,s);
const hold=join(root,'app/components/KdsHoldSheet.vue');s=await readFile(hold,'utf8');s=s.replace('    <template #body>','    <template #title><div class="flex w-full items-center gap-2"><span class="flex-1">{{code ? `Pedido ${code}` : \'Pedido\'}}</span><NuxtButton icon="i-lucide-x" square color="neutral" variant="ghost" class="ms-auto size-11" aria-label="Fechar opções do pedido" @click="emit(\'update:open\',false)"/></div></template>\n    <template #body>');await writeFile(hold,s);
// Feedback persistente adicional. Não modifica requisições, prazo, rollback ou retry.
const board=join(root,'app/composables/useKdsBoard.ts');s=await readFile(board,'utf8');s=s.replace('export function useKdsBoard(stationRef: string) {',`export function useKdsBoard(stationRef: string) {
  const previewWriteError = useState<string>('preview-kds-write-error', () => '');
  function previewReportError(message:string) { previewWriteError.value = 'Estação ' + (view.value?.instanceName || stationRef) + ': ' + message; useSonner.error(message); }
`);
s=s.replace('    enqueue(`/api/v1/backstage/kds/tickets/${pk}/done/`)', '    const previewFinishRef = findTicket(pk)?.order_ref || String(pk);\n    enqueue(`/api/v1/backstage/kds/tickets/${pk}/done/`)');
s=s.replace('        await refresh();\n        releaseFinish(pk);', '        await refresh();\n        releaseFinish(pk);\n        if(previewWriteError.value.includes(`Pedido ${previewFinishRef}.`)) previewWriteError.value = \'\';');
s=s.replaceAll('useSonner.error(httpErrorMessage','previewReportError(httpErrorMessage');
s=s.replace('previewReportError(httpErrorMessage(err, "Falha ao marcar Pronto. Tente de novo."));','previewReportError(`Pedido ${previewFinishRef}. Pronto não foi confirmado. ` + httpErrorMessage(err, "Tente novamente."));');await writeFile(board,s);
// O retorno de uma escrita que falhou continua visível nos destinos simulados.
for(const target of ['app/pages/preview/central.vue','app/pages/preview/apps/[app].vue']) {
  const path=join(root,target);let content=await readFile(path,'utf8');
  content=content.replace('<script setup lang="ts">', `<script setup lang="ts">
const previewWriteError = useState<string>('preview-kds-write-error', () => '');`);
  content=content.replace('<section ', `<div v-if="previewWriteError" class="px-3 py-2" data-preview-write-error><NuxtAlert color="error" variant="subtle" title="Ação não concluída" :description="previewWriteError" :close="{variant:'ghost',color:'neutral',class:'size-11'}" @update:open="previewWriteError=''" /></div><section `);
  await writeFile(path,content);
}
