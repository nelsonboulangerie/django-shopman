import {readFile,writeFile,copyFile} from 'node:fs/promises';
import {join} from 'node:path';
const root=process.argv[2];if(!root)throw Error('Informe a cópia temporária do KDS.');
const file=join(root,'app/pages/[ref].vue');let page=await readFile(file,'utf8');
if(page.includes('data-preview-kds-context-bar'))throw Error('Use uma cópia nova da fonte para aplicar a prévia.');
page=page.replace('label: `${action.label} ${code}`,','label: `${action.label} ${code}`,\n        shortLabel: action.label,');
page=page.replace('class="contents md:hidden"','class="relative shrink-0 md:hidden in-data-[keyboard=open]:hidden" data-preview-kds-context-bar');
const barEnd='label="Ato do pedido em foco"\n      />';
if(!page.includes(barEnd))throw Error('Revisar o encaixe da barra de ação com a fonte atual.');
page=page.replace(barEnd,barEnd+`
      <NuxtButton v-if="phoneFocus" icon="i-lucide-ellipsis-vertical" color="neutral" variant="ghost" square
        class="absolute right-5 top-4 size-11"
        :ui="{base:'text-inverted hover:bg-(--ui-text-inverted)/10 active:bg-(--ui-text-inverted)/10'}"
        :aria-label="'Opções do pedido ' + splitRef(phoneFocus.order_ref).code"
        :title="'Opções do pedido ' + splitRef(phoneFocus.order_ref).code"
        data-preview-kds-context-options
        @click="onHold(phoneFocus.pk)" />`);
page=page.replace('<span class="text-sm text-muted-foreground">Mais urgente primeiro, da esquerda para a direita.</span>',`<span class="hidden xl:inline text-sm text-muted-foreground">Mais urgente primeiro, da esquerda para a direita.</span>
        <NuxtButton class="ms-auto max-md:hidden" color="neutral" variant="ghost" icon="i-lucide-history"
          label="Histórico" aria-label="Histórico de hoje da estação" @click="historyOpen = true" data-preview-kds-history />`);
await writeFile(file,page);
await copyFile(new URL('composition.css',import.meta.url),join(root,'app/assets/css/preview-composition.css'));
let config=await readFile(join(root,'nuxt.config.ts'),'utf8');
config=config.replace('css: ["~/assets/css/tailwind.css"]','css: ["~/assets/css/tailwind.css", "~/assets/css/preview-composition.css"]');
config=config.replace('export default defineNuxtConfig({','export default defineNuxtConfig({\n  nitro: { output: { dir: ".output-proposal" } },');
await writeFile(join(root,'nuxt.config.ts'),config);
await copyFile(new URL('simulator.html',import.meta.url),join(root,'public/simulator.html')); 
