import {readFile,writeFile,copyFile} from 'node:fs/promises';
import {join} from 'node:path';
const root=process.argv[2];if(!root)throw new Error('Informe a cópia temporária do PDV.');
const here=new URL('./',import.meta.url);
for(const name of ['PosPreordersShell.vue','PosSettingsTabs.vue'])await copyFile(new URL(name,here),join(root,'app/components',name));
const page=join(root,'app/pages/preorders/index.vue');
let text=await readFile(page,'utf8');text=text.replace('label="Recortes das encomendas"','label="Recortes"');await writeFile(page,text);
await copyFile(new URL('composition.css',here),join(root,'app/assets/css/preview-composition.css'));
const config=join(root,'nuxt.config.ts');text=await readFile(config,'utf8');text=text.replace('css: ["~/assets/css/tailwind.css"]','css: ["~/assets/css/tailwind.css", "~/assets/css/preview-composition.css"]');await writeFile(config,text);

await copyFile(new URL('simulator.html',here),join(root,'public/simulator.html'));
