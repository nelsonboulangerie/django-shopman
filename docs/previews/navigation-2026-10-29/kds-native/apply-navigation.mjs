// Encaixes exclusivos do runtime temporário. Nunca escreve na árvore do produto.
import {readFile,writeFile,copyFile,mkdir} from 'node:fs/promises';
import {join,dirname} from 'node:path';
const root=process.argv[2];if(!root)throw Error('Informe a extração temporária do KDS.');
const here=new URL('./navigation/',import.meta.url),kit=join(root,'../operator-kit');
for(const name of ['KdsPreviewAppLink.vue','KdsPreviewStationMenu.vue','KdsPreviewRailMenu.vue'])await copyFile(new URL(name,here),join(root,'app/components',name));
for(const [name,to] of [['central.vue','app/pages/preview/central.vue'],['app.vue','app/pages/preview/apps/[app].vue']]){await mkdir(dirname(join(root,to)),{recursive:true});await copyFile(new URL(name,here),join(root,to));}
// Slots opcionais: o conteúdo padrão canônico segue igual onde não são usados.
const header=join(kit,'app/components/OperatorPageHeader.vue');let s=await readFile(header,'utf8');
s=s.replace(':toggle="Boolean(suiteRail)"',':toggle="Boolean(suiteRail)"\n      :toggle-side="$slots.title ? \'right\' : \'left\'"');
const titleStart=s.indexOf('      <template #title>'),titleEnd=s.indexOf('      </template>',titleStart);
if(titleStart<0||titleEnd<0)throw Error('Revisar slot de título do kit.');
s=s.slice(0,titleEnd)+'        </slot>\n'+s.slice(titleEnd);s=s.replace('<template #title>','<template #title>\n        <slot name="title">');await writeFile(header,s);
const shell=join(kit,'app/components/OperatorSuiteShell.vue');s=await readFile(shell,'utf8');
const shellStart=s.indexOf('<template #header="{ collapsed: isCollapsed }">'),shellEnd=s.indexOf('      </template>',shellStart);
if(shellStart<0||shellEnd<0)throw Error('Revisar identidade do shell.');
s=s.slice(0,shellEnd)+'        </slot>\n'+s.slice(shellEnd);s=s.replace('<template #header="{ collapsed: isCollapsed }">','<template #header="{ collapsed: isCollapsed }">\n        <slot name="identity" :collapsed="isCollapsed">');await writeFile(shell,s);
const quick=join(kit,'app/components/OperatorQuickBar.vue');s=await readFile(quick,'utf8');s=s.replace('label: "Mais",','label: "Mais",\n          active: !layout.value.items.some(section => section.key === props.current) && props.sections.some(section => section.key === props.current),');await writeFile(quick,s);
// Título de estação vira seletor; as ações são as mesmas, agrupadas pela estação.
const board=join(root,'app/pages/[ref].vue');s=await readFile(board,'utf8');s=s.replace(':actions="headerActions"',':actions="[]"');s=s.replace('      <template #status>',`      <template #lead><KdsPreviewAppLink/><KdsPreviewRailMenu/></template>
      <template #title><KdsPreviewStationMenu :title="stationTitle" :actions="headerActions"/></template>
      <template #status>`);
s=s.replace('const chosenPk = ref<number | null>(null);',"const chosenPk = useState<number | null>('preview-kds-focus-' + stationRef.value, () => null);");
s=s.replace(':eyebrow="positions.get(card.pk) ?? \'\'"',':eyebrow="positions.get(card.pk) ?? \'\'"\n                    :data-preview-kds-current="positions.get(card.pk) === queuePositionLabel(0) || undefined"');await writeFile(board,s);
const index=join(root,'app/pages/index.vue');s=await readFile(index,'utf8');s=s.replace('<OperatorPageHeader title="Estações" />','<OperatorPageHeader title="Estações"><template #lead><KdsPreviewAppLink/><KdsPreviewRailMenu/></template><template #title><KdsPreviewStationMenu title="Estações"/></template></OperatorPageHeader>');await writeFile(index,s);
const app=join(root,'app/app.vue');s=await readFile(app,'utf8');s=s.replace('const isCustomerBoard =',`const isNavigationPreview = computed(() => route.path.startsWith('/preview/'));
const returnPath = useState<string>('preview-kds-return', () => '/bancada');
watch(() => route.fullPath, path => { if(route.name === 'ref') returnPath.value = path; }, {immediate:true});
const isCustomerBoard =`);
s=s.replace('      <OperatorSuiteShell','      <div v-else-if="isNavigationPreview"><NuxtPage/></div>\n      <OperatorSuiteShell');
s=s.replace('        <!-- A trava cobre', '        <template #identity="{collapsed}"><KdsPreviewAppLink rail :collapsed="collapsed"/></template>\n        <!-- A trava cobre');await writeFile(app,s);
const sections=join(root,'app/presentation/sections.ts');s=await readFile(sections,'utf8');s=s.replace('const ordered = priority ? [priority, ...input.stations.filter((station) => station !== priority)] : [...input.stations];','const ordered = [...input.stations];');await writeFile(sections,s);
const config=join(root,'nuxt.config.ts');s=await readFile(config,'utf8');s=s.replace('runtimeConfig: {',"runtimeConfig: {\n    public: {operatorHubUrl:'/preview/central',ordersUrl:'/preview/apps/orders'},");await writeFile(config,s);
