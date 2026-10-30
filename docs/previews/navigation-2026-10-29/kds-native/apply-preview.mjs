import {readFile,writeFile,copyFile} from 'node:fs/promises';
import {join} from 'node:path';
const root=process.argv[2];if(!root)throw Error('Informe a cópia temporária do KDS.');
const file=join(root,'app/pages/[ref].vue');let page=await readFile(file,'utf8');
const marker='const phoneContext = computed(() => {';
if(!page.includes(marker))throw Error('Revisar o encaixe com a fonte atual.');
page=page.replace(marker,`// Alternativa de composição: acesso explícito ao mesmo menu do toque longo.
const phoneOptions = computed<OperatorActionBarAction | undefined>(() => phoneFocus.value && (phoneAction.value?.label.length ?? 0) < 19 ? {
  label: '', icon: 'i-lucide-ellipsis-vertical',
  ariaLabel: 'Opções do pedido ' + splitRef(phoneFocus.value.order_ref).code,
  onSelect: () => { if(phoneFocus.value) onHold(phoneFocus.value.pk); },
} : undefined);
`+marker);
page=page.replace('label: `${action.label} ${code}`,','label: `${action.label} ${code}`,\n        shortLabel: action.label,');
page=page.replace(':action="phoneAction"',':action="phoneAction"\n        :secondary="phoneOptions"');
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
