// PRÉVIA (modo compacto). Copia as duas peças compartilhadas para o operator-kit de uma
// CÓPIA temporária e acrescenta ao CSS base do kit a regra do fechar dos avisos no canto
// superior direito (decisão consolidada). Não altera nenhum componente existente do kit.
// (Testado e descartado: aviso da tela em uma linha. Ganhou 2px sobre a prévia anterior e
// sobrepôs a ação ao texto a 320px.)
import {copyFile,readFile,appendFile} from 'node:fs/promises';
import {join} from 'node:path';
const kit=process.argv[2];if(!kit)throw Error('Informe surfaces/operator-kit da cópia temporária.');
for(const n of ['OperatorCompactSeal.vue','OperatorCompactBar.vue'])await copyFile(new URL(n,import.meta.url),join(kit,'app/components',n));
const base=join(kit,'app/assets/css/operator-base.css');
if(!(await readFile(base,'utf8')).includes('PRÉVIA (decisão consolidada): o fechar'))
  await appendFile(base,await readFile(new URL('alert-dismiss.css',import.meta.url),'utf8'));
