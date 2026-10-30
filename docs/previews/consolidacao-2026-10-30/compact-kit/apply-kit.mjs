// PRÉVIA (modo compacto). Copia as duas peças compartilhadas para o operator-kit de uma
// CÓPIA temporária. Não altera nenhum componente existente do kit.
// (Testado e descartado: aviso da tela em uma linha. Ganhou 2px sobre a prévia anterior e
// sobrepôs a ação ao texto a 320px.)
import {copyFile} from 'node:fs/promises';
import {join} from 'node:path';
const kit=process.argv[2];if(!kit)throw Error('Informe surfaces/operator-kit da cópia temporária.');
for(const n of ['OperatorCompactSeal.vue','OperatorCompactBar.vue'])await copyFile(new URL(n,import.meta.url),join(kit,'app/components',n));
