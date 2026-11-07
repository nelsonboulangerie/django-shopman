// PRÉVIA C, rodada desktop do Gestor (do `md` para cima). Roda depois do apply-compact
// (que a chama no fim) ou sozinha numa cópia já compacta. Âncoras que falham alto.
//
// O que muda na mesa:
//   1. A linha do título fica com título, estado da conexão, busca, maquininha, som/Visto
//      e ⋯. Ordenar ("Urgência") e a visão (Grade | Lista) descem para o FIM da linha
//      dos recortes: são modo de ver a lista, e espremiam o título ("Ped" a 1024px,
//      "Pe" a 1280px). Abaixo do `xl` elas continuam no ⋯, como já era.
//   2. A linha dos recortes quebra em vez de rolar escondida: a 1024px "Retirada" e o
//      canal saíam da tela sem nenhum indício.
import {readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
const root=process.argv[2];if(!root)throw Error('Informe a cópia temporária do orders-nuxt.');
const file=join(root,'app/pages/index.vue');let s=await readFile(file,'utf8');
if(s.includes('data-desk-view-tools')){console.log('apply-desk: já aplicado');process.exit(0);}
function swap(from,to){const n=s.split(from).length-1;if(n!==1)throw Error(`Encaixe ${n===0?'ausente':'repetido'}: `+from.slice(0,70));s=s.replace(from,to);}
const start='        <template v-if="!compactHeader">\n          <!-- ordenar: na Fila';
const end='          <OperatorTableView v-if="view === \'table\'" table-key="orders-queue" />\n        </template>\n';
const i=s.indexOf(start),j=s.indexOf(end,i);
if(i<0||j<0)throw Error('Encaixe ausente: bloco de ordenar/visão no #actions');
const block=s.slice(i,j+end.length);s=s.slice(0,i)+s.slice(j+end.length);
const moved=block.replace('<template v-if="!compactHeader">','<div v-if="!compactHeader" class="ms-auto flex items-center gap-2 max-md:hidden" data-desk-view-tools>').replace(/<\/template>\n$/,'</div>\n').replace(":content=\"{ align: 'end' }\"",":content=\"{ align: 'end' }\"");
swap('      <template v-if="hasChannelQueueSignal" #feedback>',`      <!-- PRÉVIA (mesa): o modo de ver a lista no fim da linha dos recortes. -->
      <template #filters-end>
${moved}      </template>
      <template v-if="hasChannelQueueSignal" #feedback>`);
swap('      :filters-wrap="false"\n      :phone-actions="phoneHeaderActions"','      :phone-actions="phoneHeaderActions"');
await writeFile(file,s);console.log('apply-desk: ok');
